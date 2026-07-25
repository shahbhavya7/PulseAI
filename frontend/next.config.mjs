/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Emit a self-contained server bundle (server.js + minimal node_modules) so
  // the Docker image can run the dashboard without the full dependency tree.
  output: "standalone",
};

export default nextConfig;
