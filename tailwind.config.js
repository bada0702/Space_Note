/** @type {import('tailwindcss').Config} */
export default {
  content: [
    './index.html',
    './src/**/*.{ts,tsx}',
    // liquid-glass-react 내부가 Tailwind 클래스(bg-black, opacity-0 등)를 쓴다
    './node_modules/liquid-glass-react/dist/index.esm.js',
  ],
  darkMode: 'class',
  theme: { extend: {} },
  plugins: [],
}
