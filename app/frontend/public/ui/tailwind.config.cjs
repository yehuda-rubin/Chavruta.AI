/** v3 config mirroring the inline `tailwind.config` the CDN used — identical utilities. */
module.exports = {
  content: ['./chavruta.html'],
  theme: { extend: {
    colors: {
      ink: '#1c1a17', tekhelet: '#002045', 'tekhelet-2': '#1a365d', indigo: '#3a5ba0',
      gold: '#8a6510', 'gold-soft': '#b88f2e', cream: '#fdfbf6', 'cream-2': '#f6f1e7', line: '#ece2cf',
    },
    fontFamily: { serif: ['"Frank Ruhl Libre"', 'serif'], sans: ['Heebo', 'sans-serif'] },
  }},
}
