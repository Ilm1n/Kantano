/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type ActionStep = {
    id: string;
    tool: ActionStep.tool;
    args: Record<string, any>;
    display?: Record<string, any>;
};
export namespace ActionStep {
    export enum tool {
        CREATE_TASK = 'CreateTask',
        UPDATE_TASK = 'UpdateTask',
        MOVE_TASK = 'MoveTask',
        CREATE_COLUMN = 'CreateColumn',
        RENAME_COLUMN = 'RenameColumn',
        MOVE_COLUMN = 'MoveColumn',
        CREATE_TAG = 'CreateTag',
        UPDATE_TAG = 'UpdateTag',
        ADD_TAG_TO_TASK = 'AddTagToTask',
        REMOVE_TAG_FROM_TASK = 'RemoveTagFromTask',
    }
}
