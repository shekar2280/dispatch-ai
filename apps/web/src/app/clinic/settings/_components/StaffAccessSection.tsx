'use client';

import Image from 'next/image';
import React, { useState, useEffect, useCallback } from 'react';
import {
  Users,
  UserPlus,
  Mail,
  User,
  Trash2,
  CheckCircle2,
  Clock,
  AlertCircle,
  X,
  Loader2,
  Pencil,
  Lock,
  ShieldAlert,
  RotateCcw,
} from 'lucide-react';
import { useClinicSettings } from '../../_context/ClinicSettingsContext';
import { API_BASE_URL, APP_CONFIG } from '@/lib/constants';
import { createClient } from '@/lib/supabase/client';

interface StaffMember {
  id: string | null;
  email: string;
  full_name: string;
  role: string;
  status: 'active' | 'invited' | 'revoked';
  total_consultations?: number;
  total_minutes_worked?: number;
  total_walkins_triaged?: number;
  total_revenue_collected?: number;
  joined_at?: string | null;
  revoked_at?: string | null;
  created_at: string | null;
}

export function StaffAccessSection() {
  const { orgId, clinicName, currencySymbol } = useClinicSettings();
  const [staffList, setStaffList] = useState<StaffMember[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  const [isModalOpen, setIsModalOpen] = useState(false);
  const [inviteEmail, setInviteEmail] = useState('');
  const [inviteName, setInviteName] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const [editingMember, setEditingMember] = useState<StaffMember | null>(null);
  const [editName, setEditName] = useState('');
  const [editSubmitting, setEditSubmitting] = useState(false);

  const [memberToDelete, setMemberToDelete] = useState<StaffMember | null>(null);
  const [deleteSubmitting, setDeleteSubmitting] = useState(false);

  const getAuthHeaders = useCallback(async () => {
    const supabase = createClient();
    const { data } = await supabase.auth.getSession();
    const token = data?.session?.access_token;
    return {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    };
  }, []);

  const fetchStaff = useCallback(async () => {
    if (!orgId) return;
    try {
      setLoading(true);
      setError(null);
      const headers = await getAuthHeaders();
      const res = await fetch(`${API_BASE_URL}/api/v1/clinic/staff?org_id=${orgId}`, {
        headers,
      });
      if (!res.ok) {
        const errData = await res.json().catch(() => null);
        throw new Error(errData?.detail || 'Failed to load team roster.');
      }
      const data = await res.json();
      setStaffList(data);
    } catch (err: any) {
      setError(err?.message || 'Failed to load team roster.');
    } finally {
      setLoading(false);
    }
  }, [orgId, getAuthHeaders]);

  useEffect(() => {
    void fetchStaff();
  }, [fetchStaff]);

  const handleAddStaff = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!inviteEmail.trim() || !inviteEmail.includes('@')) {
      setError('Please provide a valid email address.');
      return;
    }
    setSubmitting(true);
    setError(null);
    setSuccessMsg(null);
    try {
      const headers = await getAuthHeaders();
      const res = await fetch(`${API_BASE_URL}/api/v1/clinic/staff?org_id=${orgId}`, {
        method: 'POST',
        headers,
        body: JSON.stringify({
          email: inviteEmail.trim().toLowerCase(),
          full_name: inviteName.trim() || 'Front Desk Staff',
          role: 'receptionist',
        }),
      });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || 'Failed to add team member.');
      }
      setSuccessMsg(`${inviteEmail.trim()} has been added to your clinic team.`);
      setInviteEmail('');
      setInviteName('');
      setIsModalOpen(false);
      await fetchStaff();
      setTimeout(() => setSuccessMsg(null), 4000);
    } catch (err: any) {
      setError(err?.message || 'Failed to add team member.');
    } finally {
      setSubmitting(false);
    }
  };

  const handleOpenEdit = (member: StaffMember) => {
    setError(null);
    setEditingMember(member);
    setEditName(member.full_name || '');
  };

  const handleUpdateStaff = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!editingMember) return;
    setEditSubmitting(true);
    setError(null);
    try {
      const headers = await getAuthHeaders();
      const res = await fetch(
        `${API_BASE_URL}/api/v1/clinic/staff/${encodeURIComponent(editingMember.email)}?org_id=${orgId}`,
        {
          method: 'PATCH',
          headers,
          body: JSON.stringify({
            full_name: editName.trim() || 'Front Desk Staff',
            role: 'receptionist',
          }),
        }
      );
      if (!res.ok) {
        const errData = await res.json().catch(() => null);
        throw new Error(errData?.detail || 'Failed to update staff member.');
      }
      setSuccessMsg(`Information updated for ${editingMember.email}.`);
      setEditingMember(null);
      await fetchStaff();
      setTimeout(() => setSuccessMsg(null), 4000);
    } catch (err: any) {
      setError(err?.message || 'Failed to update staff member.');
    } finally {
      setEditSubmitting(false);
    }
  };

  const handleConfirmDelete = async () => {
    if (!memberToDelete) return;
    setDeleteSubmitting(true);
    setError(null);
    try {
      const headers = await getAuthHeaders();
      const res = await fetch(
        `${API_BASE_URL}/api/v1/clinic/staff/${encodeURIComponent(memberToDelete.email)}?org_id=${orgId}`,
        {
          method: 'DELETE',
          headers,
        }
      );
      if (!res.ok) {
        const errData = await res.json().catch(() => null);
        throw new Error(errData?.detail || 'Failed to remove team member.');
      }
      setSuccessMsg(`Clinic access revoked for ${memberToDelete.full_name}. Their Google account and historical records are unchanged.`);
      setMemberToDelete(null);
      await fetchStaff();
      setTimeout(() => setSuccessMsg(null), 4000);
    } catch (err: any) {
      setError(err?.message || 'Failed to remove team member.');
    } finally {
      setDeleteSubmitting(false);
    }
  };

  const handleRestoreAccess = async (member: StaffMember) => {
    try {
      setLoading(true);
      setError(null);
      const headers = await getAuthHeaders();
      const res = await fetch(`${API_BASE_URL}/api/v1/clinic/staff?org_id=${orgId}`, {
        method: 'POST',
        headers,
        body: JSON.stringify({
          email: member.email,
          full_name: member.full_name,
          role: 'receptionist',
        }),
      });
      if (!res.ok) {
        const errData = await res.json().catch(() => null);
        throw new Error(errData?.detail || 'Failed to restore staff access.');
      }
      setSuccessMsg(`Access restored for ${member.full_name}.`);
      await fetchStaff();
      setTimeout(() => setSuccessMsg(null), 4000);
    } catch (err: any) {
      setError(err?.message || 'Failed to restore staff access.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-6 animate-fade-in font-sans">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-neutral-200">
        <div>
          <h3 className="text-lg font-bold text-neutral-950 tracking-tight">Clinic access</h3>
          <p className="text-xs text-neutral-500 mt-0.5">
            One clinic, one doctor. Invite receptionists using the email they use to sign in with Google.
          </p>
        </div>
        <button
          type="button"
          onClick={() => {
            setError(null);
            setIsModalOpen(true);
          }}
          className="inline-flex items-center justify-center gap-1.5 px-3.5 py-2 rounded-xl bg-neutral-950 hover:bg-neutral-800 text-white text-xs font-semibold tracking-wide transition shadow-xs cursor-pointer shrink-0"
        >
          <UserPlus className="w-3.5 h-3.5" />
          <span>Add receptionist</span>
        </button>
      </div>

      {error && (
        <div className="p-3 rounded-xl bg-rose-50 border border-rose-200/80 text-rose-800 text-xs flex items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <AlertCircle className="w-4 h-4 text-rose-600 shrink-0" />
            <span>{error}</span>
          </div>
          <button
            type="button"
            onClick={() => fetchStaff()}
            className="underline font-semibold hover:text-rose-950 cursor-pointer"
          >
            Retry
          </button>
        </div>
      )}

      {successMsg && (
        <div className="p-3 rounded-xl bg-emerald-50 border border-emerald-200/80 text-emerald-800 text-xs flex items-center gap-2">
          <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0" />
          <span>{successMsg}</span>
        </div>
      )}

      <div className="bg-white border border-neutral-200/80 rounded-2xl shadow-2xs overflow-hidden">
        <div className="px-5 py-3.5 border-b border-neutral-100 flex items-center justify-between">
          <span className="text-xs font-bold uppercase tracking-wider text-neutral-600">
            Active Roster
          </span>
          <span className="text-xs text-neutral-400 font-medium">
            {staffList.length} {staffList.length === 1 ? 'member' : 'members'}
          </span>
        </div>

        {loading ? (
          <div className="py-16 text-center text-xs text-neutral-400 flex flex-col items-center justify-center gap-2">
            <Loader2 className="w-5 h-5 animate-spin text-neutral-500" />
            <span>Loading clinic team...</span>
          </div>
        ) : staffList.length === 0 ? (
          <div className="py-16 text-center space-y-2">
            <Users className="w-8 h-8 text-neutral-300 mx-auto" />
            <p className="text-xs font-medium text-neutral-600">No team members added yet.</p>
            <p className="text-[11px] text-neutral-400">
              Click &quot;Add receptionist&quot; above to invite receptionists.
            </p>
          </div>
        ) : (
          <div className="divide-y divide-neutral-100">
            {staffList.map((member, idx) => {
              const isDoctor = member.role === 'doctor' || member.role === 'admin';
              const avatarSrc = isDoctor ? APP_CONFIG.profileIcon : APP_CONFIG.receptionistProfileIcon;

              return (
                <div
                  key={member.email || idx}
                  className="px-5 py-3.5 flex items-center justify-between hover:bg-neutral-50/50 transition gap-4"
                >
                  <div className="flex items-center gap-3.5 min-w-0">
                    <Image
                      width={36}
                      height={36}
                      src={avatarSrc}
                      alt={member.full_name}
                      className="w-9 h-9 rounded-full object-cover border border-neutral-200 bg-neutral-100 shrink-0 shadow-2xs"
                    />
                    <div className="min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-semibold text-neutral-900 truncate">
                          {member.full_name}
                        </span>
                        {isDoctor && (
                          <span className="text-[10px] font-semibold text-neutral-700 bg-neutral-100 border border-neutral-200 px-2 py-0.5 rounded-full">
                            Doctor / Owner
                          </span>
                        )}
                        {!isDoctor && (
                          <span className="text-[10px] font-semibold text-emerald-800 bg-emerald-50 border border-emerald-200 px-2 py-0.5 rounded-full">
                            Receptionist
                          </span>
                        )}
                      </div>
                      <div className="flex items-center gap-2 mt-0.5 text-xs text-neutral-500 truncate">
                        <span>{member.email}</span>
                        <span className="text-neutral-300">•</span>
                        {member.status === 'active' && (
                          <span className="text-emerald-600 font-medium flex items-center gap-1 text-[11px]">
                            <CheckCircle2 className="w-3 h-3" /> Active
                          </span>
                        )}
                        {member.status === 'invited' && (
                          <span className="text-amber-600 font-medium flex items-center gap-1 text-[11px]">
                            <Clock className="w-3 h-3" /> Invited
                          </span>
                        )}
                        {member.status === 'revoked' && (
                          <span className="text-rose-600 font-medium flex items-center gap-1 text-[11px]">
                            <ShieldAlert className="w-3 h-3" /> Access Revoked
                          </span>
                        )}
                      </div>

                      <div className="flex flex-wrap items-center gap-1.5 mt-2">
                        {isDoctor ? (
                          <>
                            <span className="inline-flex items-center gap-1 text-[11px] font-medium text-neutral-600 bg-neutral-100/90 border border-neutral-200/80 px-2 py-0.5 rounded-md">
                              <span className="font-semibold text-neutral-900">{member.total_consultations ?? 0}</span> consultations
                            </span>
                            <span className="inline-flex items-center gap-1 text-[11px] font-medium text-neutral-600 bg-neutral-100/90 border border-neutral-200/80 px-2 py-0.5 rounded-md">
                              <span className="font-semibold text-neutral-900">{member.total_minutes_worked ?? 0}</span> mins logged
                            </span>
                          </>
                        ) : (
                          <>
                            <span className="inline-flex items-center gap-1 text-[11px] font-medium text-neutral-600 bg-neutral-100/90 border border-neutral-200/80 px-2 py-0.5 rounded-md">
                              <span className="font-semibold text-neutral-900">{member.total_walkins_triaged ?? 0}</span> walk-ins triaged
                            </span>
                            <span className="inline-flex items-center gap-1 text-[11px] font-medium text-emerald-700 bg-emerald-50/80 border border-emerald-200/80 px-2 py-0.5 rounded-md">
                              <span className="font-semibold text-emerald-950">{currencySymbol}{(member.total_revenue_collected ?? 0).toLocaleString()}</span> collected
                            </span>
                          </>
                        )}
                      </div>
                    </div>
                  </div>

                  {member.role === 'receptionist' && (
                    <div className="flex items-center gap-1 shrink-0">
                      {member.status === 'revoked' ? (
                        <button
                          type="button"
                          onClick={() => handleRestoreAccess(member)}
                          className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-semibold text-neutral-900 bg-neutral-100 hover:bg-neutral-200/80 transition cursor-pointer shadow-2xs"
                          title="Restore access"
                        >
                          <RotateCcw className="w-3.5 h-3.5" />
                          <span>Restore</span>
                        </button>
                      ) : (
                        <>
                          <button
                            type="button"
                            onClick={() => handleOpenEdit(member)}
                            className="p-2 rounded-lg text-neutral-500 hover:text-neutral-900 hover:bg-neutral-100 transition cursor-pointer"
                            title="Edit receptionist"
                          >
                            <Pencil className="w-4 h-4" />
                          </button>
                          <button
                            type="button"
                            onClick={() => setMemberToDelete(member)}
                            className="p-2 rounded-lg text-neutral-400 hover:text-rose-600 hover:bg-rose-50 transition cursor-pointer"
                            title="Revoke access to this clinic"
                          >
                            <Trash2 className="w-4 h-4" />
                          </button>
                        </>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>

      {isModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40 backdrop-blur-xs animate-fade-in">
          <div className="w-full max-w-md bg-white border border-neutral-200 rounded-2xl shadow-xl overflow-hidden animate-scale-in">
            <div className="px-5 py-4 border-b border-neutral-100 flex items-center justify-between">
              <div>
                <h4 className="text-sm font-bold text-neutral-900">Add receptionist</h4>
                <p className="text-[11px] text-neutral-500 mt-0.5">
                  Authorize a receptionist to access {clinicName}.
                </p>
              </div>
              <button
                type="button"
                onClick={() => setIsModalOpen(false)}
                className="p-1.5 rounded-lg text-neutral-400 hover:text-neutral-800 hover:bg-neutral-100 transition cursor-pointer"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <form onSubmit={handleAddStaff} className="p-5 space-y-4">
              <div>
                <label className="block text-xs font-semibold text-neutral-700 mb-1.5">
                  Full Name
                </label>
                <div className="relative">
                  <User className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-neutral-400" />
                  <input
                    type="text"
                    required
                    placeholder="e.g. Pooja Sharma"
                    value={inviteName}
                    onChange={(e) => setInviteName(e.target.value)}
                    className="w-full pl-9 pr-3.5 py-2 text-xs rounded-xl border border-neutral-200 focus:outline-none focus:border-neutral-900 focus:ring-1 focus:ring-neutral-900 transition"
                  />
                </div>
              </div>

              <div>
                <label className="block text-xs font-semibold text-neutral-700 mb-1.5">
                  Google Email Address *
                </label>
                <div className="relative">
                  <Mail className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-neutral-400" />
                  <input
                    type="email"
                    required
                    placeholder="receptionist@example.com"
                    value={inviteEmail}
                    onChange={(e) => setInviteEmail(e.target.value)}
                    className="w-full pl-9 pr-3.5 py-2 text-xs rounded-xl border border-neutral-200 focus:outline-none focus:border-neutral-900 focus:ring-1 focus:ring-neutral-900 transition"
                  />
                </div>
                <p className="text-[11px] text-neutral-400 mt-1">
                  They will sign in by clicking &quot;Continue with Google&quot; using this email.
                </p>
              </div>

              <div>
                <label className="block text-xs font-semibold text-neutral-700 mb-1.5">
                  Role
                </label>
                <div className="px-3.5 py-2 rounded-xl bg-neutral-50 border border-neutral-200 text-xs font-medium text-neutral-700 flex items-center justify-between">
                  <span>Front Desk Receptionist</span>
                  <span className="text-[10px] uppercase font-bold text-neutral-500 bg-neutral-200/70 px-2 py-0.5 rounded">
                    Front Desk Only
                  </span>
                </div>
              </div>

              <div className="pt-2 flex items-center justify-end gap-2">
                <button
                  type="button"
                  onClick={() => setIsModalOpen(false)}
                  className="px-4 py-2 text-xs font-semibold text-neutral-600 hover:text-neutral-900 hover:bg-neutral-100 rounded-xl transition cursor-pointer"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={submitting}
                  className="px-4 py-2 text-xs font-semibold text-white bg-neutral-950 hover:bg-neutral-800 rounded-xl transition shadow-xs disabled:opacity-60 flex items-center gap-1.5 cursor-pointer"
                >
                  {submitting ? (
                    <><Loader2 className="w-3.5 h-3.5 animate-spin" /><span>Adding...</span></>
                  ) : (
                    <span>Add receptionist</span>
                  )}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {editingMember && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40 backdrop-blur-xs animate-fade-in">
          <div className="w-full max-w-md bg-white border border-neutral-200 rounded-2xl shadow-xl overflow-hidden animate-scale-in">
            <div className="px-5 py-4 border-b border-neutral-100 flex items-center justify-between">
              <div>
                <h4 className="text-sm font-bold text-neutral-900">Edit receptionist</h4>
                <p className="text-[11px] text-neutral-500 mt-0.5">
                  Update front desk details for {editingMember.email}.
                </p>
              </div>
              <button
                type="button"
                onClick={() => setEditingMember(null)}
                className="p-1.5 rounded-lg text-neutral-400 hover:text-neutral-800 hover:bg-neutral-100 transition cursor-pointer"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <form onSubmit={handleUpdateStaff} className="p-5 space-y-4">
              <div>
                <label className="block text-xs font-semibold text-neutral-700 mb-1.5">
                  Full Name
                </label>
                <div className="relative">
                  <User className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-neutral-400" />
                  <input
                    type="text"
                    required
                    placeholder="e.g. Pooja Sharma"
                    value={editName}
                    onChange={(e) => setEditName(e.target.value)}
                    className="w-full pl-9 pr-3.5 py-2 text-xs rounded-xl border border-neutral-200 focus:outline-none focus:border-neutral-900 focus:ring-1 focus:ring-neutral-900 transition"
                  />
                </div>
              </div>

              <div>
                <label className="block text-xs font-semibold text-neutral-700 mb-1.5">
                  Google Email Address
                </label>
                <div className="relative">
                  <Lock className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-neutral-400" />
                  <input
                    type="email"
                    disabled
                    value={editingMember.email}
                    className="w-full pl-9 pr-3.5 py-2 text-xs rounded-xl border border-neutral-200 bg-neutral-50 text-neutral-500 cursor-not-allowed select-none"
                  />
                </div>
                <p className="text-[11px] text-neutral-400 mt-1">
                  Google login email cannot be changed. To use another email, revoke this clinic access and invite the new address.
                </p>
              </div>

              <div>
                <label className="block text-xs font-semibold text-neutral-700 mb-1.5">
                  Role
                </label>
                <div className="px-3.5 py-2 rounded-xl bg-neutral-50 border border-neutral-200 text-xs font-medium text-neutral-700 flex items-center justify-between">
                  <span>Front Desk Receptionist</span>
                  <span className="text-[10px] uppercase font-bold text-neutral-500 bg-neutral-200/70 px-2 py-0.5 rounded">
                    Front Desk Only
                  </span>
                </div>
              </div>

              <div className="pt-2 flex items-center justify-end gap-2">
                <button
                  type="button"
                  onClick={() => setEditingMember(null)}
                  className="px-4 py-2 text-xs font-semibold text-neutral-600 hover:text-neutral-900 hover:bg-neutral-100 rounded-xl transition cursor-pointer"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={editSubmitting}
                  className="px-4 py-2 text-xs font-semibold text-white bg-neutral-950 hover:bg-neutral-800 rounded-xl transition shadow-xs disabled:opacity-60 flex items-center gap-1.5 cursor-pointer"
                >
                  {editSubmitting ? (
                    <><Loader2 className="w-3.5 h-3.5 animate-spin" /><span>Saving...</span></>
                  ) : (
                    <span>Save Changes</span>
                  )}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {memberToDelete && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40 backdrop-blur-xs animate-fade-in">
          <div className="w-full max-w-md bg-white border border-neutral-200 rounded-2xl shadow-xl overflow-hidden animate-scale-in">
            <div className="p-5">
              <div className="flex items-start gap-3.5">
                <div className="w-10 h-10 rounded-xl bg-rose-100 text-rose-600 flex items-center justify-center shrink-0">
                  <ShieldAlert className="w-5 h-5" />
                </div>
                <div className="flex-1 min-w-0">
                  <h4 className="text-sm font-bold text-neutral-900">Revoke clinic access</h4>
                  <p className="text-xs text-neutral-600 mt-1 leading-relaxed">
                    Are you sure you want to remove <span className="font-semibold text-neutral-950">{memberToDelete.full_name}</span> ({memberToDelete.email}) from {clinicName}?
                  </p>
                </div>
              </div>

              <div className="mt-4 p-3 rounded-xl bg-amber-50/80 border border-amber-200/80 text-[11px] text-amber-900 leading-relaxed space-y-1">
                <p className="font-semibold">Audit History Preserved & Clean Unlink:</p>
                <p className="text-amber-800">
                  Revoking access removes active permissions for this clinic while permanently preserving all past consultation records, walk-in triage counts, and billing history for audit. Their Google account and access to other clinics remain unchanged. Signing in again with the same Google account will not restore this clinic access; you must explicitly restore it.
                </p>
              </div>

              <div className="mt-5 flex items-center justify-end gap-2.5">
                <button
                  type="button"
                  disabled={deleteSubmitting}
                  onClick={() => setMemberToDelete(null)}
                  className="px-4 py-2 text-xs font-semibold text-neutral-600 hover:text-neutral-900 hover:bg-neutral-100 rounded-xl transition cursor-pointer"
                >
                  Keep Access
                </button>
                <button
                  type="button"
                  disabled={deleteSubmitting}
                  onClick={handleConfirmDelete}
                  className="px-4 py-2 text-xs font-semibold text-white bg-rose-600 hover:bg-rose-700 rounded-xl transition shadow-xs flex items-center gap-1.5 cursor-pointer disabled:opacity-60"
                >
                  {deleteSubmitting ? (
                    <><Loader2 className="w-3.5 h-3.5 animate-spin" /><span>Revoking...</span></>
                  ) : (
                    <><Trash2 className="w-3.5 h-3.5" /><span>Revoke Access</span></>
                  )}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
