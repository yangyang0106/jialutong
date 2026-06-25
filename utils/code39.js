const CODE39_PATTERNS = {
  "0": "nnnwwnwnn",
  "1": "wnnwnnnnw",
  "2": "nnwwnnnnw",
  "3": "wnwwnnnnn",
  "4": "nnnwwnnnw",
  "5": "wnnwwnnnn",
  "6": "nnwwwnnnn",
  "7": "nnnwnnwnw",
  "8": "wnnwnnwnn",
  "9": "nnwwnnwnn",
  A: "wnnnnwnnw",
  B: "nnwnnwnnw",
  C: "wnwnnwnnn",
  D: "nnnnwwnnw",
  E: "wnnnwwnnn",
  F: "nnwnwwnnn",
  G: "nnnnnwwnw",
  H: "wnnnnwwnn",
  I: "nnwnnwwnn",
  J: "nnnnwwwnn",
  K: "wnnnnnnww",
  L: "nnwnnnnww",
  M: "wnwnnnnwn",
  N: "nnnnwnnww",
  O: "wnnnwnnwn",
  P: "nnwnwnnwn",
  Q: "nnnnnnwww",
  R: "wnnnnnwwn",
  S: "nnwnnnwwn",
  T: "nnnnwnwwn",
  "*": "nwnnwnwnn"
};

function normalizeCode39Value(value) {
  return String(value || "").toUpperCase().replace(/[^A-Z0-9]/g, "");
}

function buildCode39Bars(value, narrow = 3, wide = 8) {
  const normalized = normalizeCode39Value(value);
  const encoded = `*${normalized}*`;
  const bars = [];
  Array.from(encoded).forEach((char, charIndex) => {
    const pattern = CODE39_PATTERNS[char];
    if (!pattern) return;
    Array.from(pattern).forEach((part, index) => {
      bars.push({
        key: `${charIndex}-${index}`,
        black: index % 2 === 0,
        width: part === "w" ? wide : narrow
      });
    });
    if (charIndex < encoded.length - 1) {
      bars.push({ key: `${charIndex}-gap`, black: false, width: narrow });
    }
  });
  return bars;
}

module.exports = {
  buildCode39Bars,
  normalizeCode39Value
};
