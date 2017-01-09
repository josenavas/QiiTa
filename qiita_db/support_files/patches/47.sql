-- Jan 5, 2017
-- Move the analysis to the plugin system. This is a major rewrite of the
-- database backend that supports the analysis pipeline. The code is commented
-- with details on the changes implemented here, but here is an overview of
-- the changes needed to make this transformation:
-- 1) Set new data structures to support the analysis as plugins
-- 2) Create a new type plugin to define the diversity types
-- 3) Create the new commands on the existing QIIME plugin to execute the
--    existing analyses (beta div, taxa summaries and alpha rarefaction)
-- 4) Transfer all the data in the old structures to the plugin structures
-- 5) Delete old structures

-- Create the new data structures

-- Table that links the analysis with the initial set of artifacts
CREATE TABLE qiita.analysis_artifact (
    analysis_id         bigint NOT NULL,
    artifact_id         bigint NOT NULL,
    CONSTRAINT idx_analysis_artifact_0 PRIMARY KEY (analysis_id, artifact_id)
);
CREATE INDEX idx_analysis_artifact_analysis ON qiita.analysis_artifact (analysis_id);
CREATE INDEX idx_analysis_artifact_artifact ON qiita.analysis_artifact (artifact_id);
ALTER TABLE qiita.analysis_artifact ADD CONSTRAINT fk_analysis_artifact_analysis FOREIGN KEY ( analysis_id ) REFERENCES qiita.analysis( analysis_id );
ALTER TABLE qiita.analysis_artifact ADD CONSTRAINT fk_analysis_artifact_artifact FOREIGN KEY ( artifact_id ) REFERENCES qiita.artifact( artifact_id );

DO $do$
DECLARE
    divtype_id                  bigint;
    validate_id                 bigint;
    html_summary_id             bigint;
    dm_at_id                    bigint;
    rc_at_id                    bigint;
    ts_at_id                    bigint;
    qiime_id                    bigint;
    sum_taxa_id                 bigint;
    bdiv_id                     bigint;
    arare_id                    bigint;
    srare_id                    bigint;
    st_cp_id                    bigint;
    bdiv_cp_id                  bigint;
    arare_cp_id                 bigint;
    srare_cp_id                 bigint;
    biom_at_id                  bigint;
    ts_co_id                    bigint;
    dm_co_id                    bigint;
    rc_co_id                    bigint;
    sr_co_id                    bigint;
    analysis                    RECORD;
    biom_data                   RECORD;
    job_data                    RECORD;
    initial_biom_id             bigint;
    rarefaction_job_id          UUID;
    params                      json;
    rarefied_biom_id            bigint;
    cmd_id                      bigint;
    input_artifact_id           bigint;
    proc_job_id                 UUID;
    output_artifact_type_id     bigint;
    output_artifact_id          bigint;
    cmd_out_id                  bigint;
    log_id                      bigint;
    output_filepath_id          bigint;
    tree_fp                     varchar;
BEGIN
    -- The new commands that we are going to add generate new artifact types
    -- these new artifact types are going to be added to a different plugin
    -- In interest of time and given that the artifact type system is going to
    -- change in the near future, we feel that the easiest way to transfer
    -- the current analyses results is by creating 3 different types of
    -- artifacts: (1) distance matrix -> which will include the distance matrix
    -- the principal coordinates and the emperor plots; (2) rarefaction
    -- curves -> which will include all the files generated by alpha rarefaction
    -- and (3) taxonomy summary, which will include all the files generated
    -- by summarize_taxa_through_plots.py

    -- Step 1: Create the new type plugin
    INSERT INTO qiita.software (name, version, description, environment_script, start_script, software_type_id)
        VALUES ('Diversity types', '0.1.0', 'Diversity artifacts type plugin', 'source activate qiita', 'start_diversity_types', 2)
        RETURNING software_id INTO divtype_id;

    -- Step 2: Create the validate and HTML generator commands
    INSERT INTO qiita.software_command (software_id, name, description)
        VALUES (divtype_id, 'Validate', 'Validates a new artifact of the given diversity type')
        RETURNING command_id INTO validate_id;
    INSERT INTO qiita.software_command (software_id, name, description)
        VALUES (divtype_id, 'Generate HTML summary', 'Generates the HTML summary of a given diversity type')
        RETURNING command_id INTO html_summary_id;

    -- Step 3: Add the parameters for the previous commands
    INSERT INTO qiita.command_parameter (command_id, parameter_name, parameter_type, required)
        VALUES (validate_id, 'template', 'prep_template', True),
               (validate_id, 'files', 'string', True),
               (validate_id, 'artifact_type', 'string', True),
               (html_summary_id, 'input_data', 'artifact', True);

    -- Step 4: Add the new artifact types
    INSERT INTO qiita.artifact_type (artifact_type, description, can_be_submitted_to_ebi, can_be_submitted_to_vamps)
        VALUES ('distance_matrix', 'Distance matrix holding pairwise distance between samples', False, False)
        RETURNING artifact_type_id INTO dm_at_id;
    INSERT INTO qiita.artifact_type (artifact_type, description, can_be_submitted_to_ebi, can_be_submitted_to_vamps)
        VALUES ('rarefaction_curves', 'Rarefaction curves', False, False)
        RETURNING artifact_type_id INTO rc_at_id;
    INSERT INTO qiita.artifact_type (artifact_type, description, can_be_submitted_to_ebi, can_be_submitted_to_vamps)
        VALUES ('taxa_summary', 'Taxa summary plots', False, False)
        RETURNING artifact_type_id INTO ts_at_id;

    -- Step 5: Associate each artifact with the filetypes that it accepts
    -- At this time we are going to add them as directories, just as it is done
    -- right now. We can make it fancier with the new type system.
    -- Magic number 8: the filepath_type_id for the directory
    INSERT INTO qiita.artifact_type_filepath_type (artifact_type_id, filepath_type_id, required)
        VALUES (dm_at_id, 8, True),
               (rc_at_id, 8, True),
               (ts_at_id, 8, True);

    -- Step 6: Associate the plugin with the types that it defines
    INSERT INTO qiita.software_artifact_type (software_id, artifact_type_id)
        VALUES (divtype_id, dm_at_id),
               (divtype_id, rc_at_id),
               (divtype_id, ts_at_id);

    -- Step 7: Create the new entries for the data directory
    INSERT INTO qiita.data_directory (data_type, mountpoint, subdirectory, active)
        VALUES ('distance_matrix', 'distance_matrix', true, true),
               ('rarefaction_curves', 'rarefaction_curves', true, true),
               ('taxa_summary', 'taxa_summary', true, true);

    -- Create the new commands that execute the current analyses. In qiita,
    -- the only commands that where available are Summarize Taxa, Beta
    -- Diversity and Alpha Rarefaction. The system was executing rarefaction
    -- by default, but it should be a different step in the analysis process
    -- so we are going to create a command for it too. These commands are going
    -- to be part of the QIIME plugin, so we are going to first retrieve the
    -- id of the QIIME 1.9.1 plugin, which for sure exists cause it was added
    -- in patch 33 and there is no way of removing plugins

    -- Step 1: Get the QIIME plugin id
    SELECT software_id FROM qiita.software
        WHERE name = 'QIIME' AND version = '1.9.1'
        INTO qiime_id;

    -- Step 2: Insert the new commands in the software_command table
    INSERT INTO qiita.software_command (software_id, name, description)
        VALUES (qiime_id, 'Summarize Taxa', 'Plots taxonomy summaries at different taxonomy levels')
        RETURNING command_id INTO sum_taxa_id;
    INSERT INTO qiita.software_command (software_id, name, description)
        VALUES (qiime_id, 'Beta Diversity', 'Computes and plots beta diversity results')
        RETURNING command_id INTO bdiv_id;
    INSERT INTO qiita.software_command (software_id, name, description)
        VALUES (qiime_id, 'Alpha Rarefaction', 'Computes and plots alpha rarefaction results')
        RETURNING command_id INTO arare_id;
    INSERT INTO qiita.software_command (software_id, name, description)
        VALUES (qiime_id, 'Single Rarefaction', 'Rarefies the input table by random sampling without replacement')
        RETURNING command_id INTO srare_id;

    -- Step 3: Insert the parameters for each command
    INSERT INTO qiita.command_parameter (command_id, parameter_name, parameter_type, required, default_value)
        -- Summarize Taxa
        VALUES (sum_taxa_id, 'metadata_category', 'string', False, ''),
               (sum_taxa_id, 'sort', 'bool', False, 'False'),
        -- Beta Diversity
               (bdiv_id, 'tree', 'string', False, ''),
               (bdiv_id, 'metrics', 'mchoice:["abund_jaccard","binary_chisq","binary_chord","binary_euclidean","binary_hamming","binary_jaccard","binary_lennon","binary_ochiai","binary_otu_gain","binary_pearson","binary_sorensen_dice","bray_curtis","bray_curtis_faith","bray_curtis_magurran","canberra","chisq","chord","euclidean","gower","hellinger","kulczynski","manhattan","morisita_horn","pearson","soergel","spearman_approx","specprof","unifrac","unifrac_g","unifrac_g_full_tree","unweighted_unifrac","unweighted_unifrac_full_tree","weighted_normalized_unifrac","weighted_unifrac"]', False, '["binary_jaccard","bray_curtis"]'),
        -- Alpha rarefaction
               (arare_id, 'tree', 'string', False, ''),
               (arare_id, 'num_steps', 'integer', False, 10),
               (arare_id, 'min_rare_depth', 'integer', False, 10),
               (arare_id, 'max_rare_depth', 'integer', False, 'Default'),
        -- Single rarefaction
               (srare_id, 'depth', 'integer', True, NULL),
               (srare_id, 'subsample_multinomial', 'bool', False, 'False');

    INSERT INTO qiita.command_parameter (command_id, parameter_name, parameter_type, required, default_value)
        VALUES (sum_taxa_id, 'biom_table', 'artifact', True, NULL)
        RETURNING command_parameter_id INTO st_cp_id;
    INSERT INTO qiita.command_parameter (command_id, parameter_name, parameter_type, required, default_value)
        VALUES (bdiv_id, 'biom_table', 'artifact', True, NULL)
        RETURNING command_parameter_id INTO bdiv_cp_id;
    INSERT INTO qiita.command_parameter (command_id, parameter_name, parameter_type, required, default_value)
        VALUES (arare_id, 'biom_table', 'artifact', True, NULL)
        RETURNING command_parameter_id INTO arare_cp_id;
    INSERT INTO qiita.command_parameter (command_id, parameter_name, parameter_type, required, default_value)
        VALUES (srare_id, 'biom_table', 'artifact', True, NULL)
        RETURNING command_parameter_id INTO srare_cp_id;

    -- Step 4: Connect the artifact parameters with the artifact types that
    -- they accept
    SELECT artifact_type_id INTO biom_at_id
        FROM qiita.artifact_type
        WHERE artifact_type = 'BIOM';
    INSERT INTO qiita.parameter_artifact_type (command_parameter_id, artifact_type_id)
        VALUES (st_cp_id, biom_at_id),
               (bdiv_cp_id, biom_at_id),
               (arare_cp_id, biom_at_id),
               (srare_cp_id, biom_at_id);

    -- Step 5: Add the outputs of the command.
    INSERT INTO qiita.command_output (name, command_id, artifact_type_id)
        VALUES ('taxa_summary', sum_taxa_id, ts_at_id)
        RETURNING command_output_id INTO ts_co_id;
    INSERT INTO qiita.command_output (name, command_id, artifact_type_id)
        VALUES ('distance_matrix', bdiv_id, dm_at_id)
        RETURNING command_output_id INTO dm_co_id;
    INSERT INTO qiita.command_output (name, command_id, artifact_type_id)
        VALUES ('rarefaction_curves', arare_id, rc_at_id)
        RETURNING command_output_id INTO rc_co_id;
    INSERT INTO qiita.command_output (name, command_id, artifact_type_id)
        VALUES ('rarefied_table', srare_id, biom_at_id)
        RETURNING command_output_id INTO sr_co_id;

    -- At this point we are ready to start transferring the data from the old
    -- structures to the new structures. Overview of the procedure:
    -- Step 1: Add initial set of artifacts up to rarefied table
    -- Step 2: Transfer the "analisys jobs" to processing jobs and create
    --         the analysis artifacts
    -- Fun fact: after exploring the data on the database, we realized that
    -- there are a lot of inconsistencies in the data. Unfortunately, this
    -- makes the process of trasnferring the data from the old structure
    -- to the new one a bit more challenging, as we will need to handle
    -- different special cases.

    -- Special case 1: there are jobs in the database that do not contain
    -- any information about the options used to process those parameters.
    -- However, these jobs do not have any results and all are marked either
    -- as queued or error, although no error log has been saved. Since these
    -- jobs are mainly useleess, we are going to remove them from the system
    DELETE FROM qiita.analysis_job
        WHERE job_id IN (SELECT job_id FROM qiita.job WHERE options = '{}');
    DELETE FROM qiita.job WHERE options = '{}';

    -- Special case 2: there are a fair amount of jobs (719 last time I
    -- checked) that are not attached to any analysis. Not sure how this
    -- can happen, but these orphan jobs can't be accessed from anywhere
    -- in the interface. Remove them from the system. Note that we are
    -- unlinking the files but we are not removing them from the filepath
    -- table. We will do that on the patch 47.py using the
    -- purge_filepaths function, as it will make sure that those files are
    -- not used anywhere else
    DELETE FROM qiita.job_results_filepath WHERE job_id IN (
        SELECT job_id FROM qiita.job J WHERE NOT EXISTS (
            SELECT * FROM qiita.analysis_job AJ WHERE J.job_id = AJ.job_id));
    DELETE FROM qiita.job J WHERE NOT EXISTS (
        SELECT * FROM qiita.analysis_job AJ WHERE J.job_id = AJ.job_id);

    -- Loop through all the analysis
    FOR analysis IN
        SELECT * FROM qiita.analysis
    LOOP

        -- Step 1: Add the inital set of artifacts. An analysis starts with
        -- a set of artifacts. The initial set of artifacts are biom tables
        -- generated by subseting the BIOM tables from the studies. However,
        -- the old strucures where not storing these tables, since the first
        -- step that they did was rarefy the tables. In the new analysis
        -- pipeline, that will not be the case. Thus, there are 3 substeps
        -- to successfully add the inital set of artifacts: (1) create a
        -- placeholder artifact for the non-rarefied OTU table; (2) create
        -- a single rarefaction job that rarefies such table; and (3) create
        -- the artifact resulting from the single rarefaction step
        FOR biom_data IN
            SELECT *
            FROM qiita.analysis_filepath
                JOIN qiita.filepath USING (filepath_id)
                JOIN qiita.filepath_type USING (filepath_type_id)
            WHERE analysis_id = analysis.analysis_id
                AND filepath_type = 'biom'
        LOOP
            -- Step 1.1: Create the placeholder artifact
            -- Step 1.1.a: Add the row in the artifact table
            -- Magic number 4: Visibility -> sandbox
            INSERT INTO qiita.artifact (generated_timestamp, command_id, data_type_id, command_parameters, visibility_id, artifact_type_id, submitted_to_vamps)
                VALUES (analysis.timestamp, NULL, biom_data.data_type_id, NULL, 4, biom_at_id, False)
                RETURNING artifact_id INTO initial_biom_id;
            -- Step 1.1.b: Associate the artifact with the analysis
            INSERT INTO qiita.analysis_artifact (analysis_id, artifact_id)
                VALUES (analysis.analysis_id, initial_biom_id);

            -- Step 1.2: Create the single rarefaction job
            -- Step 1.2.a: Add the row in the procesisng job table
            -- depth 1000 -> the depth information is not stored in the database
            -- We will update the correct value in patch 47.py, since we can
            -- obtain this value from the BIOM tables
            params := ('{"depth":1000,"subsample_multinomial":false,"biom_table":' || initial_biom_id::varchar || '}')::json;
            -- magic number 3: status -> success
            INSERT INTO qiita.processing_job (email, command_id, command_parameters, processing_job_status_id)
                VALUES (analysis.email, srare_id, params, 3)
                RETURNING processing_job_id INTO rarefaction_job_id;
            -- Step 1.2.b: Link the job with the input artifact
            INSERT INTO qiita.artifact_processing_job (artifact_id, processing_job_id)
                VALUES (initial_biom_id, rarefaction_job_id);

            -- Step 1.3: Create the rarefied artifact
            -- Step 1.3.a: Add the row in the artifact table
            -- Magic number 4: Visibility -> sandbox
            INSERT INTO qiita.artifact (generated_timestamp, command_id, data_type_id, command_parameters, visibility_id, artifact_type_id, submitted_to_vamps)
                VALUES (analysis.timestamp, srare_id, biom_data.data_type_id, params, 4, biom_at_id, False)
                RETURNING artifact_id INTO rarefied_biom_id;
            -- Step 1.3.b: Link the artifact with its file
            INSERT INTO qiita.artifact_filepath (artifact_id, filepath_id)
                VALUES (rarefied_biom_id, biom_data.filepath_id);
            -- Step 1.3.c: Link the artifact with its parent
            INSERT INTO qiita.parent_artifact (artifact_id, parent_id)
                VALUES (rarefied_biom_id, initial_biom_id);
            -- Step 1.3.d: Link the artifact as the job output
            INSERT INTO qiita.artifact_output_processing_job (artifact_id, processing_job_id, command_output_id)
                VALUES (rarefied_biom_id, rarefaction_job_id, sr_co_id);

            -- Step 2: Transfer all the "analysis" jobs that used this biom
            -- table as input to the new structure
            FOR job_data IN
                SELECT *
                FROM qiita.job
                WHERE reverse(split_part(reverse(options::json->>'--otu_table_fp'), '/', 1)) = biom_data.filepath
            LOOP
                -- Step 2.1: Define which command the current job executed and
                -- which are the parameters of this job
                IF job_data.command_id = 1 THEN
                    -- Taxa summaries
                    cmd_id := sum_taxa_id;
                    params := ('{"biom_table":'|| rarefied_biom_id::varchar ||',"metadata_category":"","sort":false}')::json;
                    output_artifact_type_id := ts_at_id;
                    cmd_out_id := ts_co_id;
                ELSIF job_data.command_id = 2 THEN
                    -- Beta diversity
                    cmd_id := bdiv_id;
                    params := ('{"biom_table":'|| rarefied_biom_id::varchar ||',"tree":"'|| (job_data.options::json->'tree_fp')::varchar ||'","metrics":["unweighted_unifrac","weighted_unifrac"]}')::json;
                    output_artifact_type_id := dm_at_id;
                    cmd_out_id := dm_co_id;
                ELSE
                    -- Alpha rarefaction
                    cmd_id := arare_id;
                    params := ('{"biom_table":'|| rarefied_biom_id::varchar ||',"tree":"'|| (job_data.options::json->'tree_fp')::varchar ||'","num_steps":"10","min_rare_depth":"10","max_rare_depth":"Default"}')::json;
                    output_artifact_type_id := rc_at_id;
                    cmd_out_id := rc_co_id;
                END IF;

                -- Step 2.2: Create the job
                -- Step 2.2.a: Add the row in the processing job table
                -- Magic number 3: status -> success
                INSERT INTO qiita.processing_job (email, command_id, command_parameters, processing_job_status_id)
                    VALUES (analysis.email, cmd_id, params, 3)
                    RETURNING processing_job_id INTO proc_job_id;
                -- Step 2.2.b: Link the job with the input artifact
                INSERT INTO qiita.artifact_processing_job (artifact_id, processing_job_id)
                    VALUES (rarefied_biom_id, proc_job_id);


                -- Step 2.3: Check if the executed job has results and add them
                IF EXISTS(SELECT * FROM qiita.job_results_filepath WHERE job_id = job_data.job_id) THEN
                    -- There are results for the current job
                    -- Step 2.3.a: Add the row in the artifact table
                    -- Magic number 4: Visibility -> sandbox
                    INSERT INTO qiita.artifact (generated_timestamp, command_id, data_type_id, command_parameters, visibility_id, artifact_type_id, submitted_to_vamps)
                        VALUES (analysis.timestamp, cmd_id, biom_data.data_type_id, params, 4, output_artifact_type_id, False)
                        RETURNING artifact_id INTO output_artifact_id;
                    -- Step 2.3.b: Link the artifact with its file
                    SELECT filepath_id INTO output_filepath_id FROM qiita.job_results_filepath WHERE job_id = job_data.job_id;
                    INSERT INTO qiita.artifact_filepath (artifact_id, filepath_id)
                        VALUES (output_artifact_id, output_filepath_id);
                    -- Step 2.3.c: Link the artifact with its parent
                    INSERT INTO qiita.parent_artifact (artifact_id, parent_id)
                        VALUES (output_artifact_id, rarefied_biom_id);
                    -- Step 2.3.d: Link the artifact as the job output
                    INSERT INTO qiita.artifact_output_processing_job (artifact_id, processing_job_id, command_output_id)
                        VALUES (output_artifact_id, proc_job_id, cmd_out_id);
                ELSE
                    -- There are no results on the current job, so mark it as
                    -- error
                    IF job_data.log_id IS NULL THEN
                        -- Magic number 2 - we are not using any other severity
                        -- level, so keep using number 2
                        INSERT INTO qiita.logging (time, severity_id, msg)
                            VALUES (analysis.timestamp, 2, "Unknown error - patch 47")
                            RETURNING logging_id into log_id;
                    ELSE
                        log_id := job_data.log_id;
                    END IF;

                    UPDATE qiita.processing_job
                        SET processing_job_status_id = 4, logging_id = log_id
                        WHERE processing_job_id = proc_job_id;
                END IF;
            END LOOP;
        END LOOP;
    END LOOP;
END $do$;

-- Delete old structures that are not used anymore
DROP TABLE qiita.collection_job;
DROP TABLE qiita.collection_analysis;
DROP TABLE qiita.collection_users;
DROP TABLE qiita.collection;
DROP TABLE qiita.collection_status;
DROP TABLE qiita.analysis_workflow;
DROP TABLE qiita.analysis_chain;
DROP TABLE qiita.analysis_job;
DROP TABLE qiita.job_results_filepath;
DROP TABLE qiita.job;
DROP TABLE qiita.job_status;
DROP TABLE qiita.command_data_type;
DROP TABLE qiita.command;
