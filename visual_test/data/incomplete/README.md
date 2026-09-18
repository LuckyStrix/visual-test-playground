# incomplete — legacy audit dir

Zero-byte CSVs from sessions that never logged a trial are removed on
profile switch (`DataLogger.set_participant` cleans them up), so this
directory normally stays empty. Old audit files may remain; safe to
delete.
