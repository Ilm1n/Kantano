/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ProposedAction } from './ProposedAction';
import type { RunResult } from './RunResult';
export type RunRead = {
    id: string;
    status: RunRead.status;
    provider: (string | null);
    model: (string | null);
    stepCount: number;
    fallbackUsed: boolean;
    stopRequested?: boolean;
    proposedAction: (ProposedAction | null);
    result: (RunResult | null);
    createdAt: string;
    updatedAt: string;
};
export namespace RunRead {
    export enum status {
        RUNNING = 'running',
        PENDING = 'pending',
        EXECUTING = 'executing',
        COMPLETED = 'completed',
        REJECTED = 'rejected',
        FAILED = 'failed',
        INTERRUPTED = 'interrupted',
        UNKNOWN = 'unknown',
        CANCELLED = 'cancelled',
    }
}
