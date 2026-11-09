/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: { extend: { colors: { navy: '#14233b', ink: '#18263d', mist: '#f6f8fb', line: '#e8edf3' }, boxShadow: { panel: '0 3px 16px rgba(21,40,72,.045)' } } },
  plugins: [],
}
