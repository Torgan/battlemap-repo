import type { MetadataRoute } from "next";

// Disallow all crawlers — this is a personal archive, not meant to be indexed.
export default function robots(): MetadataRoute.Robots {
  return {
    rules: { userAgent: "*", disallow: "/" },
  };
}
