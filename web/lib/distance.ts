/** Haversine distance in km between two lat/lon points */
export function haversineKm(
  lat1: number, lon1: number,
  lat2: number, lon2: number
): number {
  const R = 6371;
  const dLat = ((lat2 - lat1) * Math.PI) / 180;
  const dLon = ((lon2 - lon1) * Math.PI) / 180;
  const a =
    Math.sin(dLat / 2) ** 2 +
    Math.cos((lat1 * Math.PI) / 180) *
    Math.cos((lat2 * Math.PI) / 180) *
    Math.sin(dLon / 2) ** 2;
  return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}

/** Sort stores by distance (nearest first), then by stock (highest first) */
export function sortStoresByDistance<
  T extends { latitude: number | null; longitude: number | null; stok_adet: number }
>(stores: T[], userLat: number, userLon: number): T[] {
  return [...stores].sort((a, b) => {
    const distA =
      a.latitude && a.longitude
        ? haversineKm(userLat, userLon, a.latitude, a.longitude)
        : 99999;
    const distB =
      b.latitude && b.longitude
        ? haversineKm(userLat, userLon, b.latitude, b.longitude)
        : 99999;

    // Primary: distance (nearest first)
    // Secondary: stock (highest first)
    if (Math.abs(distA - distB) > 0.5) return distA - distB;
    return b.stok_adet - a.stok_adet;
  });
}

/** Format distance as human-readable string */
export function formatDistance(km: number): string {
  if (km < 1) return `${Math.round(km * 1000)} m`;
  return `${km.toFixed(1)} km`;
}
