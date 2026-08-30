/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { Body_upload_avatar_api_users_me_avatar_post } from '../models/Body_upload_avatar_api_users_me_avatar_post';
import type { UserPasswordUpdate } from '../models/UserPasswordUpdate';
import type { UserPublic } from '../models/UserPublic';
import type { UserRead } from '../models/UserRead';
import type { UserUpdate } from '../models/UserUpdate';
import type { CancelablePromise } from '../core/CancelablePromise';
import type { BaseHttpRequest } from '../core/BaseHttpRequest';
export class UsersService {
    constructor(public readonly httpRequest: BaseHttpRequest) {}
    /**
     * Read Users Me
     * @returns UserRead Successful Response
     * @throws ApiError
     */
    public readUsersMeApiUsersMeGet(): CancelablePromise<UserRead> {
        return this.httpRequest.request({
            method: 'GET',
            url: '/api/users/me',
        });
    }
    /**
     * Update User Me
     * @param requestBody
     * @returns UserRead Successful Response
     * @throws ApiError
     */
    public updateUserMeApiUsersMePatch(
        requestBody: UserUpdate,
    ): CancelablePromise<UserRead> {
        return this.httpRequest.request({
            method: 'PATCH',
            url: '/api/users/me',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Update User Password
     * @param requestBody
     * @returns UserRead Successful Response
     * @throws ApiError
     */
    public updateUserPasswordApiUsersMePasswordPatch(
        requestBody: UserPasswordUpdate,
    ): CancelablePromise<UserRead> {
        return this.httpRequest.request({
            method: 'PATCH',
            url: '/api/users/me/password',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Read User By Id
     * @param userId
     * @returns UserPublic Successful Response
     * @throws ApiError
     */
    public readUserByIdApiUsersUserIdGet(
        userId: number,
    ): CancelablePromise<UserPublic> {
        return this.httpRequest.request({
            method: 'GET',
            url: '/api/users/{user_id}',
            path: {
                'user_id': userId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Upload Avatar
     * @param formData
     * @returns UserRead Successful Response
     * @throws ApiError
     */
    public uploadAvatarApiUsersMeAvatarPost(
        formData: Body_upload_avatar_api_users_me_avatar_post,
    ): CancelablePromise<UserRead> {
        return this.httpRequest.request({
            method: 'POST',
            url: '/api/users/me/avatar',
            formData: formData,
            mediaType: 'multipart/form-data',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Delete Avatar
     * @returns UserRead Successful Response
     * @throws ApiError
     */
    public deleteAvatarApiUsersMeAvatarDelete(): CancelablePromise<UserRead> {
        return this.httpRequest.request({
            method: 'DELETE',
            url: '/api/users/me/avatar',
        });
    }
}
