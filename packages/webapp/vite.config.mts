import dns from 'dns';
import { execFileSync } from 'child_process';
import { join, dirname } from 'path';
import { fileURLToPath } from 'url';
import { createRequire } from 'module';

import { viteCommonjs } from '@originjs/vite-plugin-commonjs';
import legacy from '@vitejs/plugin-legacy';
import react from '@vitejs/plugin-react';
import tailwind from 'tailwindcss';
import autoprefixer from 'autoprefixer';
import { UserConfig, defineConfig, loadEnv } from 'vite';
import svgr from 'vite-plugin-svgr';
import viteTsConfigPaths from 'vite-tsconfig-paths';

// ESM-compatible __dirname and require
const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);
const require = createRequire(import.meta.url);

dns.setDefaultResultOrder('verbatim');

export default defineConfig(({ mode }): UserConfig => {
  const env = loadEnv(mode, process.cwd());
  const git = (args: string[]) => {
    try { return execFileSync('git', args, { cwd: __dirname, encoding: 'utf8' }).trim(); }
    catch { return 'unknown'; }
  };
  const buildIdentity = {
    revision: env.SIGMARAIL_BUILD_REVISION || git(['rev-parse', '--short=12', 'HEAD']),
    branch: env.SIGMARAIL_BUILD_BRANCH || git(['branch', '--show-current']),
    source_tree: env.SIGMARAIL_BUILD_TREE || git(['rev-parse', '--show-toplevel']),
  };


  // expose .env as process.env instead of import.meta since jest does not import meta yet
  const envWithProcessPrefix = Object.entries(env).reduce((prev, [key, val]) => {
    return {
      ...prev,
      ['process.env.' + key]: `"${val}"`,
    };
  }, {});

  return {
    cacheDir: '../../node_modules/.vite/webapp',

    server: {
      port: 3000,
      host: 'localhost',
      allowedHosts: ['zechariah-untainting-unvolubly.ngrok-free.dev', 'turnip.tail850cb1.ts.net'],
      open: true,
      headers: {
        // Disable caching in development to prevent stale JavaScript
        'Cache-Control': 'no-store, no-cache, must-revalidate, proxy-revalidate',
        'Pragma': 'no-cache',
        'Expires': '0',
      },
      proxy: {
        '/api': {
          target: 'http://localhost:5001',
          changeOrigin: true,
          ws: true,
          cookieDomainRewrite: 'localhost',
          secure: false,
        },
        '/static/graphene_django': {
          target: 'http://localhost:5001',
          changeOrigin: true,
        },
      },
    },

    preview: {
      port: 4300,
      host: 'localhost',
    },

    define: { ...envWithProcessPrefix, __SIGMARAIL_BUILD__: JSON.stringify(buildIdentity) },

    css: {
      postcss: {
        plugins: [tailwind({ config: join(__dirname, 'tailwind.config.ts') }), autoprefixer()],
      },
    },

    plugins: [
      legacy(),
      react(),
      viteTsConfigPaths({
        projects: ['../../tsconfig.base.json'],
      }),
      svgr({
        svgrOptions: { icon: true },
        include: ['**/*.svg', '**/*.svg?react'],
        exclude: [],
      }),
      viteCommonjs(),
    ],

    build: {
      outDir: 'build',
    },

    resolve: {
      // SigmaRail is a feature module in this webapp. Keep router context, just
      // like React context, on the single AppTension copy.
      dedupe: ['react', 'react-dom', 'react-router', 'react-router-dom'],
      // Vite 6: Default conditions changed - explicitly set if needed
      // Defaults are now: ['module', 'browser', 'development|production']
      conditions: ['module', 'browser', 'development', 'production'],
      alias: {
        'fs': require.resolve('rollup-plugin-node-builtins'),
        'path': require.resolve('rollup-plugin-node-builtins'),
      },
    },
  };
});
