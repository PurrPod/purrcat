/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        cream: '#FAF8F5',
        ink: '#1A1A1A',
        terracotta: '#D47A5A',
        paper: '#FFFFFF',
        sand: '#E8E5DF',
      },
      fontFamily: {
        serif: ['"Playfair Display"', 'Georgia', 'serif'],
        sans: ['Inter', 'ui-sans-serif', 'system-ui', 'sans-serif'],
      },
      boxShadow: {
        'soft': '0 4px 20px rgba(0,0,0,0.03)',
        'soft-hover': '0 8px 30px rgba(0,0,0,0.08)',
      },
    },
  },
  plugins: [],
}
