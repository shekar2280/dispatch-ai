export function resolveOrgId(searchParams?: URLSearchParams | null): string {
  if (typeof window !== 'undefined') {
    if (searchParams) {
      const urlOrgId = searchParams.get('org_id');
      if (urlOrgId && urlOrgId.length === 36) return urlOrgId;
    }
    const storedOrgId = localStorage.getItem('clinic_org_id');
    if (storedOrgId && storedOrgId.length === 36) return storedOrgId;
  }
  return process.env.NEXT_PUBLIC_DEFAULT_ORG_ID ?? '';
}

export function useOrgId(): string {
  if (typeof window === 'undefined') return process.env.NEXT_PUBLIC_DEFAULT_ORG_ID ?? '';
  const params = new URLSearchParams(window.location.search);
  return resolveOrgId(params);
}
