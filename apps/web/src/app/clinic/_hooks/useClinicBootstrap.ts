'use client';

import { useQuery } from '@tanstack/react-query';
import { createClient } from '@/lib/supabase/client';
import { httpClient, ApiError } from '@/lib/api/httpClient';

export async function fetchClinicBootstrap() {
  const supabase = createClient();
  const { data: { user }, error: authError } = await supabase.auth.getUser();
  if (authError || !user) throw new ApiError(401, 'Please sign in to your clinic.');

  const readClinicMembership = async () => {
    return supabase
      .from('clinic_memberships')
      .select('*, organizations(*)')
      .eq('user_id', user.id)
      .eq('status', 'active')
      .order('created_at', { ascending: true })
      .limit(1)
      .maybeSingle();
  };

  let { data: clinicMembership, error } = await readClinicMembership();
  if (error) throw error;

  if (!clinicMembership?.org_id) {
    try {
      await httpClient.post('/api/v1/clinic/staff/claim', {
        full_name: user.user_metadata?.full_name || 'Front Desk Staff',
      });
      const result = await readClinicMembership();
      clinicMembership = result.data;
      error = result.error;
    } catch {
    }

  }

  if (error && !clinicMembership?.org_id) throw error;
  if (!clinicMembership?.org_id || !clinicMembership.organizations || clinicMembership.is_active === false) {
    throw new ApiError(403, 'No active clinic membership was found.');
  }

  return {
    user,
    membership: clinicMembership,
    organization: clinicMembership.organizations,
    role: clinicMembership.role === 'receptionist' ? 'receptionist' as const : 'doctor' as const,
  };
}

export function useClinicBootstrap() {
  return useQuery({
    queryKey: ['clinic-bootstrap'],
    queryFn: fetchClinicBootstrap,
    staleTime: Infinity,
    retry: false,
  });
}
