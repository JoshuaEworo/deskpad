"""Outbound-only Cloudflare signaling client. All peer negotiation is signed."""

import asyncio
import json
import logging
import secrets
import time

import httpx
from websockets.asyncio.client import connect

from .identity import b64

log = logging.getLogger("deskpad")


class Remote:
    def __init__(self, identity, settings, service, rtc):
        self.identity, self.settings, self.service, self.rtc = identity, settings, service, rtc
        self.pending, self.challenges = {}, {}
        self.socket = None
        self.stopping = False
        self.task = None
        self.negotiating = set()
        self.jobs = set()

    def pairing_url(self):
        i = self.identity
        fragment = b64(
            json.dumps(
                {
                    "v": 2,
                    "room": i.room,
                    "gate": i.gate,
                    "host": i.public,
                    "invite": i.invite,
                    "name": self.settings.name,
                },
                separators=(",", ":"),
            ).encode()
        )
        return self.settings.service_url + "/#deskpad=" + fragment

    def refresh(self):
        i = self.identity
        self.service.update(
            devices=[{"id": k, **v} for k, v in i.devices.items()],
            pending=[
                {"id": k, "name": p["name"], "code": i.pairing_code(p["key"])}
                for k, p in self.pending.items()
                if p["expires"] > time.time()
            ],
        )

    async def start(self):
        if self.task:
            return
        if not self.settings.service_url:
            self.service.update(remote_status="Remote service not configured")
            return
        self.stopping = False
        self.new_invite()
        self.task = asyncio.create_task(self.run())

    async def stop(self):
        self.stopping = True
        if self.task:
            self.task.cancel()
            await asyncio.gather(self.task, return_exceptions=True)
            self.task = None
        for job in self.jobs:
            job.cancel()
        await asyncio.gather(*self.jobs, return_exceptions=True)
        self.jobs.clear()
        self.pending.clear()
        self.challenges.clear()
        for owner in list(self.rtc.peers):
            if owner.startswith("remote:"):
                await self.rtc.peers[owner].close()
        self.refresh()
        self.service.update(remote_status="Local only")

    async def send(self, target, body):
        if self.socket:
            await self.socket.send(json.dumps({"to": target, "message": self.identity.sign(body)}))

    async def run(self):
        i = self.identity
        url = self.settings.service_url
        headers = {"Authorization": "Bearer " + i.owner}
        delay = 1
        while not self.stopping:
            try:
                self.service.update(remote_status="Connecting to service…")
                async with httpx.AsyncClient(timeout=15) as client:
                    result = await client.put(
                        f"{url}/api/rooms/{i.room}", headers=headers, json={"gate": i.gate}
                    )
                    result.raise_for_status()
                    enrollment = result.json().get("enrollmentRequired", False)
                socket_url = url.replace("https://", "wss://", 1) + f"/api/rooms/{i.room}/socket"
                async with connect(
                    socket_url,
                    additional_headers=headers,
                    max_size=131072,
                    ping_interval=20,
                    ping_timeout=20,
                ) as socket:
                    self.socket = socket
                    self.service.update(
                        remote_status="Finish remote setup in your browser"
                        if enrollment
                        else "Available anywhere",
                        remote_url="" if enrollment else self.pairing_url(),
                        setup_url=url
                        + "/#setup="
                        + b64(json.dumps({"room": i.room, "owner": i.owner}).encode())
                        if enrollment
                        else "",
                    )
                    delay = 1
                    async for raw in socket:
                        packet = json.loads(raw)
                        if packet.get("event") == "activated":
                            self.service.update(
                                remote_status="Available anywhere",
                                remote_url=self.pairing_url(),
                                setup_url="",
                            )
                            continue
                        if packet.get("left"):
                            self.challenges.pop(packet["left"], None)
                            self.pending = {
                                k: v
                                for k, v in self.pending.items()
                                if v["target"] != packet["left"]
                            }
                            self.refresh()
                            continue
                        job = asyncio.create_task(self.handle(packet["from"], packet["message"]))
                        self.jobs.add(job)
                        job.add_done_callback(self.jobs.discard)
            except asyncio.CancelledError:
                break
            except Exception:
                # No URLs, QR fragments, SDP, tokens, or credentials in logs.
                self.service.update(remote_status="Service unreachable; retrying")
                log.warning("Remote signaling disconnected")
            finally:
                self.socket = None
                self.challenges.clear()
                self.pending.clear()
                self.refresh()
            await asyncio.sleep(delay)
            delay = min(30, delay * 2)

    async def ice(self):
        i = self.identity
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.post(
                f"{self.settings.service_url}/api/rooms/{i.room}/ice",
                headers={"Authorization": "Bearer " + i.owner},
            )
            response.raise_for_status()
            return response.json()["iceServers"]

    async def handle(self, target, envelope):
        try:
            identifier, public, value = self.identity.check(envelope)
            kind, nonce = value.get("kind"), value["nonce"]
            if kind == "pair":
                i = self.identity
                if time.time() > i.invite_until or not secrets.compare_digest(
                    str(value.get("invite", "")), i.invite
                ):
                    raise ValueError("Pairing code expired. Scan a new QR code on the laptop.")
                self.pending = {k: v for k, v in self.pending.items() if v["expires"] > time.time()}
                if len(self.pending) >= 8:
                    raise ValueError("Too many pending pairing requests")
                self.pending[identifier] = {
                    "key": public,
                    "name": str(value.get("name", "Phone"))[:64],
                    "nonce": nonce,
                    "target": target,
                    "expires": time.time() + 120,
                }
                self.refresh()
                await self.send(
                    target,
                    {"kind": "pending", "nonce": nonce, "code": self.identity.pairing_code(public)},
                )
                return
            if identifier not in self.identity.devices:
                raise ValueError("Approve this phone on the laptop first")
            if self.rtc.paused() or not self.settings.remote:
                raise ValueError("Laptop connections are paused")
            if kind == "connect":
                if self.rtc.lease["id"] or self.negotiating:
                    raise ValueError("Laptop is already in use")
                now = time.time()
                self.challenges = {k: v for k, v in self.challenges.items() if v["expires"] > now}
                if len(self.challenges) >= 8:
                    raise ValueError("Too many connection requests")
                challenge = secrets.token_urlsafe(32)
                # Reserve this slot before awaiting credential generation.
                self.challenges[target] = {
                    "id": identifier,
                    "challenge": challenge,
                    "expires": now + 60,
                    "ice": [],
                }
                ice = await self.ice()
                if target not in self.challenges:
                    return
                self.challenges[target]["ice"] = ice
                await self.send(
                    target,
                    {
                        "kind": "config",
                        "nonce": nonce,
                        "challenge": challenge,
                        "ice": ice,
                        "name": self.settings.name,
                    },
                )
            elif kind == "offer":
                entry = self.challenges.pop(target, None)
                if not entry or (
                    entry["id"] != identifier
                    or entry["expires"] < time.time()
                    or value.get("challenge") != entry["challenge"]
                ):
                    raise ValueError("Connection challenge expired")
                if identifier in self.negotiating:
                    raise ValueError("Connection in progress")
                self.negotiating.add(identifier)
                owner = "remote:" + identifier
                try:
                    answer = await self.rtc.offer(owner, value.get("sdp"), entry["ice"])
                    await self.send(target, {"kind": "answer", "nonce": nonce, "sdp": answer})
                finally:
                    self.negotiating.discard(identifier)
        except asyncio.CancelledError:
            raise
        except Exception as error:
            # Error text must never echo untrusted payloads or credentials.
            message = (
                str(error)
                if isinstance(error, ValueError)
                else "Connection could not be established"
            )
            await self.send(
                target,
                {"kind": "error", "nonce": locals().get("nonce", ""), "message": message[:180]},
            )

    async def approve(self, identifier):
        entry = self.pending.pop(identifier, None)
        if not entry or entry["expires"] < time.time():
            raise ValueError("Pairing request expired")
        self.identity.approve(identifier, entry["key"], entry["name"])
        self.refresh()
        await self.send(entry["target"], {"kind": "approved", "nonce": entry["nonce"]})

    async def revoke(self, identifier):
        self.identity.revoke(identifier)
        self.challenges = {k: v for k, v in self.challenges.items() if v["id"] != identifier}
        peer = self.rtc.peers.get("remote:" + identifier)
        if peer:
            await peer.close()
        self.refresh()

    def new_invite(self):
        self.identity.invite = secrets.token_urlsafe(32)
        self.identity.invite_until = time.time() + 600
        self.service.update(remote_url=self.pairing_url())
