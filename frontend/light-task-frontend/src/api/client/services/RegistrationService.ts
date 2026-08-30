/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ConfirmRegistrationRequest } from '../models/ConfirmRegistrationRequest';
import type { EmailConfirmed } from '../models/EmailConfirmed';
import type { RegistrationAccepted } from '../models/RegistrationAccepted';
import type { RegistrationRequest } from '../models/RegistrationRequest';
import type { ResendVerificationRequest } from '../models/ResendVerificationRequest';
import type { VerificationTokenRequest } from '../models/VerificationTokenRequest';
import type { CancelablePromise } from '../core/CancelablePromise';
import type { BaseHttpRequest } from '../core/BaseHttpRequest';
export class RegistrationService {
    constructor(public readonly httpRequest: BaseHttpRequest) {}
    /**
     * Register
     * @param requestBody
     * @returns RegistrationAccepted Successful Response
     * @throws ApiError
     */
    public registerApiRegistrationPost(
        requestBody: RegistrationRequest,
    ): CancelablePromise<RegistrationAccepted> {
        return this.httpRequest.request({
            method: 'POST',
            url: '/api/registration',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Resend Verification
     * @param requestBody
     * @returns RegistrationAccepted Successful Response
     * @throws ApiError
     */
    public resendVerificationApiRegistrationResendPost(
        requestBody: ResendVerificationRequest,
    ): CancelablePromise<RegistrationAccepted> {
        return this.httpRequest.request({
            method: 'POST',
            url: '/api/registration/resend',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Confirm
     * @param requestBody
     * @returns EmailConfirmed Successful Response
     * @throws ApiError
     */
    public confirmApiRegistrationConfirmPost(
        requestBody: ConfirmRegistrationRequest,
    ): CancelablePromise<EmailConfirmed> {
        return this.httpRequest.request({
            method: 'POST',
            url: '/api/registration/confirm',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Validate Token
     * @param requestBody
     * @returns void
     * @throws ApiError
     */
    public validateTokenApiRegistrationValidatePost(
        requestBody: VerificationTokenRequest,
    ): CancelablePromise<void> {
        return this.httpRequest.request({
            method: 'POST',
            url: '/api/registration/validate',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
}
