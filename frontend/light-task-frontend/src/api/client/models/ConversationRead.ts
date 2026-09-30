/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type ConversationRead = {
    id: string;
    projectId: number;
    title: string;
    mode: ConversationRead.mode;
    createdAt: string;
    updatedAt: string;
};
export namespace ConversationRead {
    export enum mode {
        LOCAL = 'local',
        CLOUD = 'cloud',
    }
}
