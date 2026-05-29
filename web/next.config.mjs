/** @type {import('next').NextConfig} */
const nextConfig = {
  images: {
    // R2 public bucket + Reddit CDN. Set R2 host via env at build if you use next/image.
    remotePatterns: [
      { protocol: "https", hostname: "**.r2.dev" },
      { protocol: "https", hostname: "**.r2.cloudflarestorage.com" },
      { protocol: "https", hostname: "i.redd.it" },
    ],
  },
};

export default nextConfig;
