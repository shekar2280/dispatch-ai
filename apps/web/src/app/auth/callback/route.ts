import { createServerClient } from '@supabase/ssr';
import { NextRequest, NextResponse } from 'next/server';

export async function GET(request: NextRequest) {
  const code = request.nextUrl.searchParams.get('code');
  const targetPath = request.nextUrl.searchParams.get('next') === '/signup' ? '/signup' : '/clinic';

  const targetUrl = request.nextUrl.clone();
  targetUrl.pathname = targetPath;
  targetUrl.search = '';
  const response = NextResponse.redirect(targetUrl);

  if (code) {
    const supabase = createServerClient(
      process.env.NEXT_PUBLIC_SUPABASE_URL!,
      (process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY || process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY)!,
      {
        cookies: {
          getAll() {
            return request.cookies.getAll();
          },
          setAll(cookiesToSet: Array<{ name: string; value: string; options?: any }>) {
            cookiesToSet.forEach(({ name, value, options }) => {
              response.cookies.set(name, value, options);
            });
          },
        },
      }
    );

    const { error } = await supabase.auth.exchangeCodeForSession(code);
    if (error) {
      const loginUrl = request.nextUrl.clone();
      loginUrl.pathname = '/login';
      loginUrl.search = '';
      loginUrl.searchParams.set('error', 'confirmation_failed');
      const failedResponse = NextResponse.redirect(loginUrl);
      response.cookies.getAll().forEach((cookie) => failedResponse.cookies.set(cookie));
      return failedResponse;
    }
  } else {
    const loginUrl = request.nextUrl.clone();
    loginUrl.pathname = '/login';
    loginUrl.search = '';
    loginUrl.searchParams.set('error', 'confirmation_failed');
    return NextResponse.redirect(loginUrl);
  }

  return response;
}

