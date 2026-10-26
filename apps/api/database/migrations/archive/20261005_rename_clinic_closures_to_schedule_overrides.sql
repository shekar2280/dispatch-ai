DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'clinic_closures') THEN
    ALTER TABLE public.clinic_closures RENAME TO schedule_overrides;
  END IF;
  IF EXISTS (SELECT 1 FROM pg_indexes WHERE schemaname = 'public' AND indexname = 'idx_clinic_closures_dates') THEN
    ALTER INDEX public.idx_clinic_closures_dates RENAME TO idx_schedule_overrides_dates;
  END IF;
END $$;
