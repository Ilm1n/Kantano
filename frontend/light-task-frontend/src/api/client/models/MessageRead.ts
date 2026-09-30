/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { TaskReference } from './TaskReference';
export type MessageRead = {
    id: string;
    role: MessageRead.role;
    content: string;
    references: Array<TaskReference>;
    createdAt: string;
};
export namespace MessageRead {
    export enum role {
        USER = 'user',
        ASSISTANT = 'assistant',
    }
}
