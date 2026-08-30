/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { BaseHttpRequest } from './core/BaseHttpRequest';
import type { OpenAPIConfig } from './core/OpenAPI';
import { AxiosHttpRequest } from './core/AxiosHttpRequest';
import { AuthService } from './services/AuthService';
import { BoardsService } from './services/BoardsService';
import { DefaultService } from './services/DefaultService';
import { InvitationsService } from './services/InvitationsService';
import { ProjectsService } from './services/ProjectsService';
import { RegistrationService } from './services/RegistrationService';
import { TagsService } from './services/TagsService';
import { UsersService } from './services/UsersService';
type HttpRequestConstructor = new (config: OpenAPIConfig) => BaseHttpRequest;
export class KantanoClient {
    public readonly auth: AuthService;
    public readonly boards: BoardsService;
    public readonly default: DefaultService;
    public readonly invitations: InvitationsService;
    public readonly projects: ProjectsService;
    public readonly registration: RegistrationService;
    public readonly tags: TagsService;
    public readonly users: UsersService;
    public readonly request: BaseHttpRequest;
    constructor(config?: Partial<OpenAPIConfig>, HttpRequest: HttpRequestConstructor = AxiosHttpRequest) {
        this.request = new HttpRequest({
            BASE: config?.BASE ?? '',
            VERSION: config?.VERSION ?? '0.1.0',
            WITH_CREDENTIALS: config?.WITH_CREDENTIALS ?? false,
            CREDENTIALS: config?.CREDENTIALS ?? 'include',
            TOKEN: config?.TOKEN,
            USERNAME: config?.USERNAME,
            PASSWORD: config?.PASSWORD,
            HEADERS: config?.HEADERS,
            ENCODE_PATH: config?.ENCODE_PATH,
        });
        this.auth = new AuthService(this.request);
        this.boards = new BoardsService(this.request);
        this.default = new DefaultService(this.request);
        this.invitations = new InvitationsService(this.request);
        this.projects = new ProjectsService(this.request);
        this.registration = new RegistrationService(this.request);
        this.tags = new TagsService(this.request);
        this.users = new UsersService(this.request);
    }
}

