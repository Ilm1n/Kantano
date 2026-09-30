/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ConversationRead } from './ConversationRead';
import type { MessageRead } from './MessageRead';
import type { RunRead } from './RunRead';
export type ChatDetail = {
    conversation: ConversationRead;
    messages: Array<MessageRead>;
    latestRun: (RunRead | null);
};
