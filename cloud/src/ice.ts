export interface IceServer {
  urls: string | string[];
  username?: string;
  credential?: string;
}
// Port 53 is blocked by browsers and can stall non-trickle ICE discovery.
export function usableIceServers(servers: IceServer[]): IceServer[] {
  return servers.flatMap((server) => {
    const urls = (
      typeof server.urls === "string" ? [server.urls] : server.urls
    ).filter((url) => !/:53(?:\?|$)/.test(url));
    return urls.length ? [{ ...server, urls }] : [];
  });
}
