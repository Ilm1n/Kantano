/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { CancelablePromise } from '../core/CancelablePromise';
import type { BaseHttpRequest } from '../core/BaseHttpRequest';
export class DefaultService {
    constructor(public readonly httpRequest: BaseHttpRequest) {}
    /**
     * Health Check
     * @returns any Successful Response
     * @throws ApiError
     */
    public healthCheckApiHealthGet(): CancelablePromise<any> {
        return this.httpRequest.request({
            method: 'GET',
            url: '/api/health',
        });
    }
    /**
     * Readiness Check
     * @returns any Successful Response
     * @throws ApiError
     */
    public readinessCheckApiHealthReadyGet(): CancelablePromise<any> {
        return this.httpRequest.request({
            method: 'GET',
            url: '/api/health/ready',
        });
    }
}
