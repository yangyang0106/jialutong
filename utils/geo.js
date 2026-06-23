const EARTH_RADIUS_METERS = 6371000;

function toRadians(degrees) {
  return (degrees * Math.PI) / 180;
}

function calculateDistance(fromLatitude, fromLongitude, toLatitude, toLongitude) {
  const latitudeDelta = toRadians(toLatitude - fromLatitude);
  const longitudeDelta = toRadians(toLongitude - fromLongitude);
  const fromLatitudeRadians = toRadians(fromLatitude);
  const toLatitudeRadians = toRadians(toLatitude);

  const haversine =
    Math.sin(latitudeDelta / 2) ** 2 +
    Math.cos(fromLatitudeRadians) *
      Math.cos(toLatitudeRadians) *
      Math.sin(longitudeDelta / 2) ** 2;

  return Math.round(
    EARTH_RADIUS_METERS * 2 * Math.atan2(Math.sqrt(haversine), Math.sqrt(1 - haversine))
  );
}

function calculateDistanceToSegment(latitude, longitude, start, end) {
  if (!start || !end) return null;
  const referenceLatitude = toRadians((start.latitude + end.latitude) / 2);
  const toXY = (point) => ({
    x: EARTH_RADIUS_METERS * toRadians(point.longitude) * Math.cos(referenceLatitude),
    y: EARTH_RADIUS_METERS * toRadians(point.latitude)
  });
  const point = toXY({ latitude, longitude });
  const segmentStart = toXY(start);
  const segmentEnd = toXY(end);
  const deltaX = segmentEnd.x - segmentStart.x;
  const deltaY = segmentEnd.y - segmentStart.y;
  const lengthSquared = deltaX * deltaX + deltaY * deltaY;
  if (!lengthSquared) {
    return calculateDistance(latitude, longitude, start.latitude, start.longitude);
  }
  const projection = Math.max(
    0,
    Math.min(
      1,
      ((point.x - segmentStart.x) * deltaX + (point.y - segmentStart.y) * deltaY) / lengthSquared
    )
  );
  const nearestX = segmentStart.x + projection * deltaX;
  const nearestY = segmentStart.y + projection * deltaY;
  return Math.round(Math.hypot(point.x - nearestX, point.y - nearestY));
}

function normalizePolyline(polyline) {
  if (!Array.isArray(polyline)) return [];
  if (polyline.length && typeof polyline[0] === "object") return polyline;
  const points = [];
  for (let index = 0; index < polyline.length - 1; index += 2) {
    points.push({ latitude: Number(polyline[index]), longitude: Number(polyline[index + 1]) });
  }
  return points;
}

function calculateDistanceToPolyline(latitude, longitude, polyline) {
  const points = normalizePolyline(polyline);
  if (!points.length) return null;
  if (points.length === 1) {
    return calculateDistance(latitude, longitude, points[0].latitude, points[0].longitude);
  }
  let closest = Infinity;
  for (let index = 1; index < points.length; index += 1) {
    closest = Math.min(
      closest,
      calculateDistanceToSegment(latitude, longitude, points[index - 1], points[index])
    );
  }
  return Math.round(closest);
}

module.exports = {
  calculateDistance,
  calculateDistanceToPolyline,
  calculateDistanceToSegment,
  normalizePolyline
};
