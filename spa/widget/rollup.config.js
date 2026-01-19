import resolve from '@rollup/plugin-node-resolve';
import replace from '@rollup/plugin-replace';
import typescript from '@rollup/plugin-typescript';
import { terser } from 'rollup-plugin-terser';
import copy from 'rollup-plugin-copy';

const production = process.env.BUILD === 'production';

export default {
  input: 'src/index.ts',
  output: {
    file: 'dist/widget.js',
    format: 'iife',
    name: 'InnomightChat',
    sourcemap: !production,
  },
  plugins: [
    resolve({
      browser: true,
    }),
    replace({
      preventAssignment: true,
      'process.env.NODE_ENV': JSON.stringify(production ? 'production' : 'development'),
    }),
    typescript({
      tsconfig: './tsconfig.json',
      declaration: false,
      declarationDir: undefined,
    }),
    copy({
      targets: [
        { src: 'public/*', dest: 'dist' }
      ]
    }),
    production && terser({
      compress: {
        drop_console: true,
        drop_debugger: true,
      },
      mangle: true,
    }),
  ].filter(Boolean),
};
