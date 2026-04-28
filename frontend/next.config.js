/** @type {import('next').NextConfig} */
const isDev = process.env.NODE_ENV === "development";

const nextConfig = {
  // Keep dev and production artifacts isolated to avoid cache corruption
  // when switching between `next dev` and `next build`.
  distDir: isDev ? ".next-dev" : ".next",
};

module.exports = nextConfig;
