export const smokeEnvironment = {
  ...process.env,
  NEXT_DIST_DIR: '.next-smoke',
  NEXT_PUBLIC_SUPABASE_URL: 'https://example.supabase.co',
  NEXT_PUBLIC_SUPABASE_ANON_KEY: 'smoke-test-public-placeholder',
  NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY: '',
  NEXT_PUBLIC_API_BASE_URL: 'http://127.0.0.1:8000',
};
