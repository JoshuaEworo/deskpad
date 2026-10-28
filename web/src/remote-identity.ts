export type RemoteConfig = {
  v: 2;
  room: string;
  gate: string;
  host: JsonWebKey;
  invite?: string;
  name: string;
  approved?: boolean;
};
export type Envelope = { payload: string; signature: string; key?: JsonWebKey };
export const encode = (value: Uint8Array) =>
  btoa(String.fromCharCode(...value))
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=+$/, "");
export const decode = (value: string) =>
  Uint8Array.from(atob(value.replace(/-/g, "+").replace(/_/g, "/")), (c) =>
    c.charCodeAt(0),
  );
export const nonce = () => encode(crypto.getRandomValues(new Uint8Array(24)));
const utf8 = new TextEncoder();
const digest = async (value: string) =>
  Array.from(
    new Uint8Array(await crypto.subtle.digest("SHA-256", utf8.encode(value))),
  )
    .map((v) => v.toString(16).padStart(2, "0"))
    .join("");
export async function keyID(key: JsonWebKey) {
  // Match Python json.dumps(sort_keys=True), including spaces.
  return digest(
    JSON.stringify({ crv: "P-256", kty: "EC", x: key.x, y: key.y })
      .replace(/:/g, ": ")
      .replace(/,/g, ", "),
  );
}
export async function pairingCode(host: JsonWebKey, phone: JsonWebKey) {
  return (await digest((await keyID(host)) + (await keyID(phone))))
    .slice(0, 8)
    .toUpperCase();
}
function validate(value: RemoteConfig): RemoteConfig {
  if (
    value.v !== 2 ||
    !/^[\w-]{43}$/.test(value.room) ||
    !/^[\w-]{43}$/.test(value.gate) ||
    value.host?.crv !== "P-256" ||
    value.host?.kty !== "EC" ||
    value.host.d ||
    !/^[\w-]{43}$/.test(value.host.x || "") ||
    !/^[\w-]{43}$/.test(value.host.y || "")
  )
    throw new Error("Invalid pairing link");
  return value;
}
export function remoteConfig(): RemoteConfig | undefined {
  if (location.hash.startsWith("#deskpad=")) {
    const fragment = location.hash.slice(9);
    history.replaceState(null, "", location.pathname);
    if (fragment.length > 2048) throw new Error("Invalid pairing link");
    const value = validate(
      JSON.parse(new TextDecoder().decode(decode(fragment))),
    );
    const old = localStorage.getItem("deskpad.remote");
    // Never replace a pinned host key silently for the same remembered laptop.
    if (old) {
      const saved = validate(JSON.parse(old));
      if (
        saved.room === value.room &&
        (saved.host.x !== value.host.x || saved.host.y !== value.host.y)
      )
        throw new Error(
          "Laptop identity changed. Remove the saved pairing before pairing again.",
        );
      if (saved.room === value.room) value.approved = saved.approved;
    }
    localStorage.setItem("deskpad.remote", JSON.stringify(value));
    return value;
  }
  const stored = localStorage.getItem("deskpad.remote");
  return stored ? validate(JSON.parse(stored)) : undefined;
}
export function saveRemote(config: RemoteConfig) {
  localStorage.setItem("deskpad.remote", JSON.stringify(config));
}
export function forgetRemote() {
  localStorage.removeItem("deskpad.remote");
}
export async function phoneKeys(room: string): Promise<CryptoKeyPair> {
  const db = await new Promise<IDBDatabase>((resolve, reject) => {
    const request = indexedDB.open("deskpad-identities", 1);
    request.onupgradeneeded = () => request.result.createObjectStore("keys");
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
  const existing = await new Promise<CryptoKeyPair | undefined>(
    (resolve, reject) => {
      const request = db.transaction("keys").objectStore("keys").get(room);
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error);
    },
  );
  if (existing) {
    db.close();
    return existing;
  }
  const keys = await crypto.subtle.generateKey(
    { name: "ECDSA", namedCurve: "P-256" },
    false,
    ["sign", "verify"],
  );
  await new Promise<void>((resolve, reject) => {
    const transaction = db.transaction("keys", "readwrite");
    transaction.objectStore("keys").put(keys, room);
    transaction.oncomplete = () => resolve();
    transaction.onerror = () => reject(transaction.error);
  });
  db.close();
  return keys;
}
export async function sign(
  keys: CryptoKeyPair,
  value: unknown,
): Promise<Envelope> {
  const payload = JSON.stringify(value);
  return {
    payload,
    signature: encode(
      new Uint8Array(
        await crypto.subtle.sign(
          { name: "ECDSA", hash: "SHA-256" },
          keys.privateKey,
          utf8.encode(payload),
        ),
      ),
    ),
    key: await crypto.subtle.exportKey("jwk", keys.publicKey),
  };
}
export async function verify(envelope: Envelope, host: JsonWebKey) {
  if (typeof envelope.payload !== "string" || envelope.payload.length > 120000)
    throw new Error("Invalid signed response");
  const key = await crypto.subtle.importKey(
    "jwk",
    host,
    { name: "ECDSA", namedCurve: "P-256" },
    false,
    ["verify"],
  );
  if (
    !(await crypto.subtle.verify(
      { name: "ECDSA", hash: "SHA-256" },
      key,
      decode(envelope.signature),
      utf8.encode(envelope.payload),
    ))
  )
    throw new Error("Laptop identity verification failed");
  return JSON.parse(envelope.payload);
}
