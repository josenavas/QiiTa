-- Nov 22, 2014
-- Adding new tables to support whole genome sequencing data

CREATE TABLE qiita.assembler ( 
	assembler_id         bigserial  NOT NULL,
	name                 varchar  NOT NULL,
	version              varchar  NOT NULL,
	parameters_table     varchar  NOT NULL,
	CONSTRAINT pk_assembler PRIMARY KEY ( assembler_id )
 ) ;

CREATE TABLE qiita.culture_collection ( 
	culture_collection_name varchar  NOT NULL,
	todo_fields          varchar  ,
	CONSTRAINT pk_culture_collection PRIMARY KEY ( culture_collection_name )
 ) ;

CREATE TABLE qiita.processed_data_metadata ( 
	processed_data_id    bigint  NOT NULL,
	length               integer  NOT NULL,
	num_contigs          integer  NOT NULL,
	max_contig_length    integer  NOT NULL,
	min_contig_length    integer  NOT NULL,
	avg_contig_length    integer  NOT NULL,
	n50                  integer  NOT NULL,
	n90                  integer  NOT NULL,
	CONSTRAINT pk_processed_data_metadata PRIMARY KEY ( processed_data_id )
 ) ;

CREATE TABLE qiita.processed_params_assembler ( 
	processed_params_id  bigint  NOT NULL,
	assembler_id         bigint  NOT NULL,
	parameters_id        bigint  NOT NULL,
	CONSTRAINT pk_processed_params_assembler PRIMARY KEY ( processed_params_id )
 ) ;

CREATE INDEX idx_processed_params_assembler ON qiita.processed_params_assembler ( assembler_id ) ;

CREATE TABLE qiita.storage_conditions ( 
	storage_conditions_id bigserial  NOT NULL,
	temperature          real  ,
	todo_fields          varchar  ,
	CONSTRAINT pk_storage_conditions PRIMARY KEY ( storage_conditions_id )
 ) ;

COMMENT ON TABLE qiita.storage_conditions IS 'Information about how the strain is being stored';

COMMENT ON COLUMN qiita.storage_conditions.todo_fields IS 'Other fields to be described by the Gordon Lab.';

CREATE TABLE qiita.strain ( 
	strain_id            bigserial  NOT NULL,
	unofficial_name      varchar  NOT NULL,
	official_name        varchar  ,
	taxonomy             varchar  ,
	sequence_filepath_id bigint  ,
	sample_id            varchar  NOT NULL,
	isolation_date       timestamp  NOT NULL,
	isolation_description varchar  NOT NULL,
	storage_conditions_id bigint  NOT NULL,
	culture_collection_name varchar  ,
	todo_properties      varchar  ,
	CONSTRAINT pk_strain PRIMARY KEY ( strain_id ),
	CONSTRAINT idx_strain_3 UNIQUE ( unofficial_name ) 
 ) ;

CREATE INDEX idx_strain ON qiita.strain ( storage_conditions_id ) ;

CREATE INDEX idx_strain_0 ON qiita.strain ( culture_collection_name ) ;

CREATE INDEX idx_strain_1 ON qiita.strain ( sample_id ) ;

CREATE INDEX idx_strain_2 ON qiita.strain ( sequence_filepath_id ) ;

COMMENT ON COLUMN qiita.strain.taxonomy IS 'The Gordon Lab potentially wants more information about the taxonomy. Eg: how it was assigned, publications, morphological/phenotypic information, if available.
Potentially create a new table in which each level is it`s own column, so it is easier to query.';

COMMENT ON COLUMN qiita.strain.todo_properties IS 'The complete list of properties is still to be defined, so just putting a placeholder here for now, and once we have more information we can put them here.';

ALTER TABLE qiita.processed_data_metadata ADD CONSTRAINT fk_processed_data_metadata FOREIGN KEY ( processed_data_id ) REFERENCES qiita.processed_data( processed_data_id )    ;

ALTER TABLE qiita.processed_params_assembler ADD CONSTRAINT fk_processed_params_assembler FOREIGN KEY ( assembler_id ) REFERENCES qiita.assembler( assembler_id )    ;

ALTER TABLE qiita.strain ADD CONSTRAINT fk_strain_storage_conditions FOREIGN KEY ( storage_conditions_id ) REFERENCES qiita.storage_conditions( storage_conditions_id )    ;

ALTER TABLE qiita.strain ADD CONSTRAINT fk_strain_culture_collection FOREIGN KEY ( culture_collection_name ) REFERENCES qiita.culture_collection( culture_collection_name )    ;

ALTER TABLE qiita.strain ADD CONSTRAINT fk_strain_required_sample_info FOREIGN KEY ( sample_id ) REFERENCES qiita.required_sample_info( sample_id )    ;

ALTER TABLE qiita.strain ADD CONSTRAINT fk_strain_filepath FOREIGN KEY ( sequence_filepath_id ) REFERENCES qiita.filepath( filepath_id )    ;

ALTER TABLE qiita.prep_template ADD strain_id bigint  ;

CREATE INDEX idx_prep_template_1 ON qiita.prep_template ( strain_id ) ;

ALTER TABLE qiita.prep_template ADD CONSTRAINT fk_prep_template_strain FOREIGN KEY ( strain_id ) REFERENCES qiita.strain( strain_id )    ;

-- Add the new filetype
INSERT INTO qiita.filetype (type) VALUES ('WGS-FASTQ');

-- Add the new data type
INSERT INTO qiita.data_type (data_type) VALUES ('Single Genome');

-- Add a new mountpoint for the strains
INSERT INTO qiita.data_directory (data_type, mountpoint, subdirectory, active) VALUES ('strain', 'strains', '', true);
