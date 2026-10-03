import { createServer } from 'vite';

process.env.VITE_DATA_MODE = 'static';
process.env.VITE_BUNDLE_URL ||= './';
process.env.VITE_BASE_PATH ||= '/';

const server = await createServer();
await server.listen();
server.printUrls();

const stop = async () => {
  await server.close();
  process.exit(0);
};

process.once('SIGINT', stop);
process.once('SIGTERM', stop);
