'use client';

import React from 'react';
import { X, Phone, Clock, Activity, FileText } from 'lucide-react';
import { motion, AnimatePresence } from 'motion/react';
import { ClinicLivePatient, PatientRecordItem } from '../types';

interface PatientHistoryDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  patient: ClinicLivePatient | null;
  patientRecord?: PatientRecordItem | null;
}

export function PatientHistoryDrawer({
  isOpen,
  onClose,
  patient,
  patientRecord,
}: PatientHistoryDrawerProps) {
  if (!isOpen || !patient) return null;

  const bloodGroup = patient.blood_group || patientRecord?.blood_group;
  const rawAllergies = patient.allergies || patientRecord?.allergies;
  const allergiesDisplay = Array.isArray(rawAllergies) ? rawAllergies.join(', ') : (rawAllergies || '');
  const rawChronic = patient.chronic_conditions || patientRecord?.chronic_conditions;
  const chronicConditionsDisplay = Array.isArray(rawChronic) ? rawChronic.join(', ') : (rawChronic || '');
  const notes = patientRecord?.notes || (patient.doctor_notes ? [patient.doctor_notes] : []);

  return (
    <AnimatePresence>
      <div className="fixed inset-0 z-50 overflow-hidden flex justify-end">
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          onClick={onClose}
          className="fixed inset-0 bg-[#0D2622]/40 backdrop-blur-xs transition-opacity"
        />

        <motion.div
          initial={{ x: '100%' }}
          animate={{ x: 0 }}
          exit={{ x: '100%' }}
          transition={{ type: 'spring', damping: 28, stiffness: 280 }}
          className="relative w-full max-w-md bg-[#FFFFFF] h-full shadow-2xl flex flex-col z-10 border-l border-[rgba(13,38,34,0.16)]"
        >
          <div className="p-4 border-b border-[rgba(13,38,34,0.1)] flex items-center justify-between bg-[#F1F4EE] shrink-0">
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-sm font-bold text-[#0D2622]">Patient Medical History</h2>
                <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-[#E3EBE0] text-[#0D2622] font-semibold border border-[rgba(13,38,34,0.1)]">
                  Quick View
                </span>
              </div>
              <p className="text-xs text-[rgba(13,38,34,0.65)] mt-0.5">Previous visits and clinical records</p>
            </div>
            <button
              type="button"
              onClick={onClose}
              className="p-1 rounded-lg hover:bg-[#E3EBE0] text-[rgba(13,38,34,0.5)] hover:text-[#0D2622] transition-colors cursor-pointer"
            >
              <X className="w-4 h-4" />
            </button>
          </div>

          <div className="flex-1 overflow-y-auto p-4 space-y-4">
            <div className="p-3.5 rounded-xl bg-[#FFFFFF] border border-[rgba(13,38,34,0.14)] shadow-2xs space-y-2">
              <div className="flex items-center justify-between">
                <h3 className="text-base font-bold text-[#0D2622]">{patient.patient_name}</h3>
                {bloodGroup && (
                  <span className="text-[10px] font-mono font-bold px-2 py-0.5 rounded-full bg-rose-50 text-rose-700 border border-rose-200">
                    {bloodGroup}
                  </span>
                )}
              </div>
              <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-[rgba(13,38,34,0.65)]">
                <span className="flex items-center gap-1 font-mono">
                  <Phone className="w-3 h-3 text-[rgba(13,38,34,0.45)]" />
                  {patient.patient_phone || 'Not recorded'}
                </span>
                <span className="text-[rgba(13,38,34,0.3)]">•</span>
                <span className="flex items-center gap-1">
                  <Clock className="w-3 h-3 text-[rgba(13,38,34,0.45)]" />
                  Today: {patient.appointment_time}
                </span>
              </div>
            </div>

            <div className="space-y-2">
              <h4 className="text-[10px] font-mono font-semibold uppercase tracking-wider text-[rgba(13,38,34,0.5)]">
                Current Reason for Visit
              </h4>
              <div className="p-3 rounded-lg bg-[#F1F4EE]/60 border border-[rgba(13,38,34,0.12)] text-xs font-semibold text-[#0D2622]">
                {patient.chief_complaint || 'General consultation & routine checkup'}
              </div>
            </div>

            <div className="grid grid-cols-2 gap-2.5">
              <div className="p-3 rounded-lg bg-[#FFFFFF] border border-[rgba(13,38,34,0.14)] shadow-2xs">
                <span className="text-[10px] font-mono font-semibold text-[rgba(13,38,34,0.5)] uppercase tracking-wider block">
                  Allergies
                </span>
                <p className="text-xs font-bold text-[#0D2622] mt-1">
                  {allergiesDisplay || 'None known'}
                </p>
              </div>
              <div className="p-3 rounded-lg bg-[#FFFFFF] border border-[rgba(13,38,34,0.14)] shadow-2xs">
                <span className="text-[10px] font-mono font-semibold text-[rgba(13,38,34,0.5)] uppercase tracking-wider block">
                  Chronic Illness
                </span>
                <p className="text-xs font-bold text-[#0D2622] mt-1">
                  {chronicConditionsDisplay || 'None reported'}
                </p>
              </div>
            </div>

            {patient.recent_diagnosis && (
              <div className="space-y-1.5">
                <h4 className="text-[10px] font-mono font-semibold uppercase tracking-wider text-[rgba(13,38,34,0.5)] flex items-center gap-1">
                  <Activity className="w-3 h-3 text-[#1E6B56]" />
                  Last Diagnosis
                </h4>
                <div className="p-3 rounded-lg bg-[#FFFFFF] border border-[rgba(13,38,34,0.14)] text-xs font-bold text-[#0D2622] shadow-2xs">
                  {patient.recent_diagnosis}
                </div>
              </div>
            )}

            <div className="space-y-2">
              <h4 className="text-[10px] font-mono font-semibold uppercase tracking-wider text-[rgba(13,38,34,0.5)] flex items-center gap-1">
                <FileText className="w-3 h-3 text-[#1E6B56]" />
                Past Visit Notes
              </h4>
              {notes.length > 0 ? (
                <div className="space-y-2">
                  {notes.map((note, idx) => (
                    <div key={idx} className="p-3 rounded-lg bg-[#FFFFFF] border border-[rgba(13,38,34,0.14)] text-xs text-[rgba(13,38,34,0.85)] shadow-2xs leading-relaxed">
                      {note}
                    </div>
                  ))}
                </div>
              ) : (
                <div className="p-4 rounded-lg bg-[#F1F4EE]/40 border border-dashed border-[rgba(13,38,34,0.16)] text-center text-xs text-[rgba(13,38,34,0.5)]">
                  No prior consultation notes recorded for this patient.
                </div>
              )}
            </div>
          </div>

          <div className="p-3 border-t border-[rgba(13,38,34,0.1)] bg-[#F1F4EE] shrink-0 flex justify-end">
            <button
              type="button"
              onClick={onClose}
              className="px-4 h-8 rounded-lg bg-[#0D2622] hover:bg-[#143530] text-[#F1F4EE] text-xs font-semibold shadow-2xs transition-colors cursor-pointer"
            >
              Close
            </button>
          </div>
        </motion.div>
      </div>
    </AnimatePresence>
  );
}
