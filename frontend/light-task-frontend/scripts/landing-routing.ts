import type { Connect, Plugin } from "vite";

const documentFallback: Connect.NextHandleFunction = (req, _res, next) => {
  const path = (req.url ?? "/").split("?")[0]!;
  const isResource =
    /\.(css|js|mjs|ts|vue|map|png|webp|jpe?g|svg|ico|woff2?|xml|txt|webmanifest|html)$/.test(
      path,
    );
  if (
    req.headers.accept?.includes("text/html") &&
    path !== "/" &&
    !path.startsWith("/api/") &&
    !path.startsWith("/ws/") &&
    !isResource
  ) {
    req.url = "/app.html";
  }
  next();
};

// Match Caddy's document fallback without rewriting API or asset requests.
export function landingRouting(): Plugin {
  return {
    name: "landing-routing",
    configureServer(server) {
      server.middlewares.use(documentFallback);
    },
    configurePreviewServer(server) {
      server.middlewares.use(documentFallback);
    },
  };
}
