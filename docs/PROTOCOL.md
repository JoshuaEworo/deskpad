# Wire protocol v1

All routes are on the host's origin. JSON messages have a discriminating `type` and reject unknown fields. Protocol changes require a version bump when old clients would behave incorrectly. No replay queue exists.

## HTTP

| Route | Meaning |
| --- | --- |
| `GET /api/status` | `{protocol:1,demo:boolean,paired:boolean,busy:boolean}` |
| `POST /api/pair` | `{code:"123456"}`; sets an opaque HttpOnly device cookie |
| `POST /api/forget` | Revokes current cookie and removes it |

Mutations require an approved Origin. Bad pair attempts are limited per source and globally. Cookies, screen frames, and credentials must not be logged. Status/auth responses are not cacheable.

## Control

`/ws/control` requires the cookie and an approved Origin. An exclusive lease is assigned before accepting the socket. Successful opening receives `{type:"hello",protocol:1,connection:string,demo:boolean,cursor:[x,y]}`. Competing connections are rejected; browser handshakes may surface rejection as generic code 1006, so the client checks HTTP status.

| Input type | Fields | Semantics |
| --- | --- | --- |
| `move` | `dx,dy`: finite numbers ±2000 | Relative desktop pixels |
| `button` | `button:left/right`, `action:down/up/click` | Owned held button or atomic click |
| `scroll` | `dx,dy`: finite numbers ±100 | Wheel notches; positive y is page downward |
| `text` | `text`: 1–4096 characters | Committed Unicode; no implicit keyboard layout |
| `key` | `key`: allowlisted name; `action:down/up/press` | Named desktop key |
| `shortcut` | `keys`: 1–5 allowlisted names | Press in order, release temporary keys in reverse |
| `release` | none | Release session-owned held inputs |
| `ping` | `timestamp`: finite number | Host echoes `pong` and timestamp |

Key allowlist: Ctrl (`Control`), Alt, Shift, Windows (`Meta`), Enter, Tab, Escape, Backspace, Delete, arrows, Home, End, PageUp/PageDown, a–z, F1–F12. Pointer movement produces `{type:"cursor",position:[x,y]}`. Invalid messages produce `{type:"error",message:string}` and perform no input.

Server receive deadline: eight seconds. Client pings every two seconds. Session finally cleanup releases owned inputs even without a client release message. The client also releases on blur and closes on hidden/pagehide. Stale input is never restored after reconnect.

## Video

`/ws/video?connection=<control-connection-id>` requires both the owning device cookie and active control connection identifier. At most one video socket is admitted.

For each frame:

1. Host sends JSON: `{type:"frame",sequence,width,height,bounds:{left,top,width,height},cursor:[x,y]}`.
2. Host sends one binary JPEG message.
3. Phone decodes, displays the image, then sends the literal text `ack`.
4. Host captures the next fresh frame after the FPS pacing interval.

The host does not capture/send the next frame before acknowledgement. No historical frame queue. Ack timeout closes video; the client reconnects the session. Closing control invalidates its associated video lease. Host and client apply bounded messages/buffers. Metadata bounds are native desktop coordinates; encoded dimensions may be smaller.
