import {defineConfig} from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  base:process.env.TPAW_BASE_PATH||'/',
  plugins: [react()],
  worker: {format:'es'},
  server: {host: '127.0.0.1', strictPort: true},
  build: {sourcemap: false,outDir:process.env.TPAW_BUILD_DIR||'dist'},
})
