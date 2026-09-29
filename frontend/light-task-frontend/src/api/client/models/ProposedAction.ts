/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ActionCall } from './ActionCall';
import type { ActionDisplay } from './ActionDisplay';
export type ProposedAction = {
    name: ProposedAction.name;
    args: Record<string, any>;
    display?: (ActionDisplay | null);
    action_id?: (string | null);
    tool_call_id: string;
    calls?: (Array<ActionCall> | null);
};
export namespace ProposedAction {
    export enum name {
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
        EXECUTE_PLAN = 'ExecutePlan',
    }
}
