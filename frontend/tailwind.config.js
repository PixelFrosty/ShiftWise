/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./src/**/*.{html,ts}",
  ],
  theme: {
    extend: {
      colors: {
        brand: {
          50:  '#F5ECD1',   // Cream (light backgrounds)
          100: '#F5ECD1',   // Cream
          200: '#d4dcff',   // Light blue tint
          300: '#b3c0ff',   // Medium-light blue
          500: '#8AA4FF',   // Blue Regatta (primary)
          600: '#8AA4FF',   // Blue Regatta (buttons)
          700: '#6B88E8',   // Darker blue (hover)
          800: '#292521',   // Charcoal
          900: '#292521',   // Charcoal
        }
      }
    },
  },
  plugins: [],
};
