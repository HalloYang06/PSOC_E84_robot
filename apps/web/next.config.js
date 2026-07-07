/** @type {import('next').NextConfig} */
const distDir = process.env.NEXT_DIST_DIR?.trim();

const nextConfig = {
  reactStrictMode: true,
  staticPageGenerationTimeout: 180,
  experimental: {
    webpackBuildWorker: false,
  },
  async redirects() {
    return [
      {
        source: "/rehab-arm-mobile",
        destination: "/rehab-arm-mobile/home.html",
        permanent: false,
      },
    ];
  },
  ...(distDir ? { distDir } : {}),
};

module.exports = nextConfig;
