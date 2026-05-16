/** @type {import('next').NextConfig} */
const distDir = process.env.NEXT_DIST_DIR?.trim();

const nextConfig = {
  reactStrictMode: true,
  staticPageGenerationTimeout: 180,
  experimental: {
    webpackBuildWorker: false,
  },
  ...(distDir ? { distDir } : {}),
};

module.exports = nextConfig;
