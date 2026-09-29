/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type ActionOutcome = {
    status?: ActionOutcome.status;
    tool?: ('CreateTask' | 'UpdateTask' | 'MoveTask' | 'CreateColumn' | 'RenameColumn' | 'MoveColumn' | 'CreateTag' | 'UpdateTag' | 'AddTagToTask' | 'RemoveTagFromTask' | null);
    action_id?: (string | null);
    step_id?: (string | null);
    kind?: ('created' | 'updated' | 'moved' | 'column_created' | 'column_renamed' | 'column_moved' | 'tag_created' | 'tag_updated' | 'tag_added_to_task' | 'tag_removed_from_task' | null);
    task_id?: (number | null);
    column_id?: (number | null);
    tag_id?: (number | null);
    title?: (string | null);
    name?: (string | null);
    error?: (string | null);
    error_code?: (string | null);
};
export namespace ActionOutcome {
    export enum status {
        COMPLETED = 'completed',
        REJECTED = 'rejected',
        FAILED = 'failed',
        SKIPPED = 'skipped',
    }
}
