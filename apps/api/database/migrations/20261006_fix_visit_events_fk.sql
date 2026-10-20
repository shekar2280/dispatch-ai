-- Existing databases may have visit_events_visit_id_fkey with the default
-- NO ACTION behavior from the original appointment state migration.
-- Appointment cancellation remains a soft status update; this only governs
-- deliberate hard deletion during test cleanup or tenant data purges.
DO $$
BEGIN
    IF to_regclass('public.visit_events') IS NOT NULL
       AND to_regclass('public.appointments') IS NOT NULL THEN
        ALTER TABLE public.visit_events
            DROP CONSTRAINT IF EXISTS visit_events_visit_id_fkey;
        ALTER TABLE public.visit_events
            ADD CONSTRAINT visit_events_visit_id_fkey
            FOREIGN KEY (visit_id)
            REFERENCES public.appointments(id)
            ON DELETE CASCADE;
    END IF;
END $$;
