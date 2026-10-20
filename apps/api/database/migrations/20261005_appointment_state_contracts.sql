-- Separate waiting-room and clinical progress from booking disposition.
ALTER TABLE appointments
    ADD COLUMN IF NOT EXISTS queue_state text NOT NULL DEFAULT 'not_checked_in',
    ADD COLUMN IF NOT EXISTS encounter_state text NOT NULL DEFAULT 'not_started',
    ADD COLUMN IF NOT EXISTS called_at timestamptz,
    ADD COLUMN IF NOT EXISTS call_count integer NOT NULL DEFAULT 0;

UPDATE appointments
SET queue_state = CASE
        WHEN status::text = 'arrived' THEN 'waiting'
        WHEN status::text = 'skipped' THEN 'stepped_out'
        WHEN status::text IN ('in_progress', 'completed') THEN 'served'
        ELSE 'not_checked_in'
    END,
    encounter_state = CASE
        WHEN status::text = 'in_progress' THEN 'in_progress'
        WHEN status::text = 'completed' THEN 'completed'
        ELSE 'not_started'
    END
WHERE queue_state = 'not_checked_in' AND encounter_state = 'not_started';

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'appointments_queue_state_check') THEN
        ALTER TABLE appointments ADD CONSTRAINT appointments_queue_state_check
            CHECK (queue_state IN ('not_checked_in', 'waiting', 'called', 'stepped_out', 'served'));
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'appointments_encounter_state_check') THEN
        ALTER TABLE appointments ADD CONSTRAINT appointments_encounter_state_check
            CHECK (encounter_state IN ('not_started', 'in_progress', 'completed'));
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS visit_events (
    id uuid PRIMARY KEY,
    visit_id uuid NOT NULL REFERENCES appointments(id) ON DELETE CASCADE,
    org_id uuid NOT NULL,
    event_type text NOT NULL,
    occurred_at timestamptz NOT NULL DEFAULT now(),
    actor_id uuid,
    actor_type text NOT NULL DEFAULT 'staff',
    notes text,
    event_metadata jsonb NOT NULL DEFAULT '{}'::jsonb
);

-- The table may already have been created by an earlier version of this
-- migration. Replace the old NO ACTION constraint in-place so appointment
-- cleanup cannot fail on dependent visit history.
DO $$
BEGIN
    IF to_regclass('public.visit_events') IS NOT NULL THEN
        ALTER TABLE public.visit_events
            DROP CONSTRAINT IF EXISTS visit_events_visit_id_fkey;
        ALTER TABLE public.visit_events
            ADD CONSTRAINT visit_events_visit_id_fkey
            FOREIGN KEY (visit_id) REFERENCES public.appointments(id)
            ON DELETE CASCADE;
    END IF;
END $$;
ALTER TABLE visit_events
    ADD COLUMN IF NOT EXISTS actor_id uuid,
    ADD COLUMN IF NOT EXISTS actor_type text NOT NULL DEFAULT 'staff',
    ADD COLUMN IF NOT EXISTS notes text,
    ADD COLUMN IF NOT EXISTS event_metadata jsonb NOT NULL DEFAULT '{}'::jsonb;
CREATE INDEX IF NOT EXISTS visit_events_visit_time_idx
    ON visit_events (org_id, visit_id, occurred_at);
ALTER TABLE visit_events ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON visit_events FROM PUBLIC, anon, authenticated;
