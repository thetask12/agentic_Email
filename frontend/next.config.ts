import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Produces .next/standalone — a minimal, dependency-free server bundle
  // used by the combined Docker image (see /Dockerfile, /start.py) so the
  // container doesn't need to ship node_modules for the frontend.
  output: "standalone",
};

export default nextConfig;
