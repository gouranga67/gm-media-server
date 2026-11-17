ALTER TABLE jobs
ADD COLUMN composition jsonb NOT NULL DEFAULT '{"mode":"auto","foreground_asset_id":null,"background_asset_id":null,"chroma_key_color":"#00FF00","chroma_similarity":0.12,"chroma_blend":0.08,"spill_suppression":0.15}'::jsonb;

ALTER TABLE jobs
ADD CONSTRAINT jobs_composition_object_check
CHECK (jsonb_typeof(composition) = 'object');
