/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ActionDecision } from '../models/ActionDecision';
import type { ChatDetail } from '../models/ChatDetail';
import type { ConversationCreate } from '../models/ConversationCreate';
import type { ConversationRead } from '../models/ConversationRead';
import type { MessageCreate } from '../models/MessageCreate';
import type { CancelablePromise } from '../core/CancelablePromise';
import type { BaseHttpRequest } from '../core/BaseHttpRequest';
export class AssistantService {
    constructor(public readonly httpRequest: BaseHttpRequest) {}
    /**
     * List Conversations
     * @param projectId
     * @returns ConversationRead Successful Response
     * @throws ApiError
     */
    public listConversationsApiProjectsProjectIdAssistantConversationsGet(
        projectId: number,
    ): CancelablePromise<Array<ConversationRead>> {
        return this.httpRequest.request({
            method: 'GET',
            url: '/api/projects/{project_id}/assistant/conversations',
            path: {
                'project_id': projectId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Create Conversation
     * @param projectId
     * @param requestBody
     * @returns ConversationRead Successful Response
     * @throws ApiError
     */
    public createConversationApiProjectsProjectIdAssistantConversationsPost(
        projectId: number,
        requestBody: ConversationCreate,
    ): CancelablePromise<ConversationRead> {
        return this.httpRequest.request({
            method: 'POST',
            url: '/api/projects/{project_id}/assistant/conversations',
            path: {
                'project_id': projectId,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Get Conversation
     * @param projectId
     * @param conversationId
     * @returns ChatDetail Successful Response
     * @throws ApiError
     */
    public getConversationApiProjectsProjectIdAssistantConversationsConversationIdGet(
        projectId: number,
        conversationId: string,
    ): CancelablePromise<ChatDetail> {
        return this.httpRequest.request({
            method: 'GET',
            url: '/api/projects/{project_id}/assistant/conversations/{conversation_id}',
            path: {
                'project_id': projectId,
                'conversation_id': conversationId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Delete Conversation
     * @param projectId
     * @param conversationId
     * @returns void
     * @throws ApiError
     */
    public deleteConversationApiProjectsProjectIdAssistantConversationsConversationIdDelete(
        projectId: number,
        conversationId: string,
    ): CancelablePromise<void> {
        return this.httpRequest.request({
            method: 'DELETE',
            url: '/api/projects/{project_id}/assistant/conversations/{conversation_id}',
            path: {
                'project_id': projectId,
                'conversation_id': conversationId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Start Run
     * @param projectId
     * @param conversationId
     * @param requestBody
     * @returns any Successful Response
     * @throws ApiError
     */
    public startRunApiProjectsProjectIdAssistantConversationsConversationIdRunsPost(
        projectId: number,
        conversationId: string,
        requestBody: MessageCreate,
    ): CancelablePromise<any> {
        return this.httpRequest.request({
            method: 'POST',
            url: '/api/projects/{project_id}/assistant/conversations/{conversation_id}/runs',
            path: {
                'project_id': projectId,
                'conversation_id': conversationId,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Decide Action
     * @param projectId
     * @param conversationId
     * @param runId
     * @param requestBody
     * @returns any Successful Response
     * @throws ApiError
     */
    public decideActionApiProjectsProjectIdAssistantConversationsConversationIdRunsRunIdDecisionPost(
        projectId: number,
        conversationId: string,
        runId: string,
        requestBody: ActionDecision,
    ): CancelablePromise<any> {
        return this.httpRequest.request({
            method: 'POST',
            url: '/api/projects/{project_id}/assistant/conversations/{conversation_id}/runs/{run_id}/decision',
            path: {
                'project_id': projectId,
                'conversation_id': conversationId,
                'run_id': runId,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Stop Run
     * @param projectId
     * @param conversationId
     * @param runId
     * @returns void
     * @throws ApiError
     */
    public stopRunApiProjectsProjectIdAssistantConversationsConversationIdRunsRunIdStopPost(
        projectId: number,
        conversationId: string,
        runId: string,
    ): CancelablePromise<void> {
        return this.httpRequest.request({
            method: 'POST',
            url: '/api/projects/{project_id}/assistant/conversations/{conversation_id}/runs/{run_id}/stop',
            path: {
                'project_id': projectId,
                'conversation_id': conversationId,
                'run_id': runId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
}
