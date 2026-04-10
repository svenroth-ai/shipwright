import '@testing-library/jest-dom';
import { server } from './mocks/server';
import { afterAll, afterEach, beforeAll } from 'vitest';

beforeAll(() => server.listen({ onUnhandledRequest: 'warn' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());
