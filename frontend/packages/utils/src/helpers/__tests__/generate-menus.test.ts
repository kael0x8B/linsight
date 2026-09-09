import type { Router, RouteRecordRaw } from 'vue-router';

import { createRouter, createWebHistory } from 'vue-router';

import { describe, expect, it, vi } from 'vitest';

import {
  convertServerMenuToRouteRecordStringComponent,
  generateMenus,
} from '../generate-menus';

// Nested route setup to test child inclusion and hideChildrenInMenu functionality

describe('generateMenus', () => {
  // 模拟路由数据
  const mockRoutes = [
    {
      meta: { icon: 'home-icon', title: '首页' },
      name: 'home',
      path: '/home',
    },
    {
      meta: { hideChildrenInMenu: true, icon: 'about-icon', title: '关于' },
      name: 'about',
      path: '/about',
      children: [
        {
          path: 'team',
          name: 'team',
          meta: { icon: 'team-icon', title: '团队' },
        },
      ],
    },
  ] as RouteRecordRaw[];

  // 模拟 Vue 路由器实例
  const mockRouter = {
    getRoutes: vi.fn(() => [
      { name: 'home', path: '/home' },
      { name: 'about', path: '/about' },
      { name: 'team', path: '/about/team' },
    ]),
  };

  it('the correct menu list should be generated according to the route', async () => {
    const expectedMenus = [
      {
        badge: undefined,
        badgeType: undefined,
        badgeVariants: undefined,
        icon: 'home-icon',
        name: '首页',
        order: undefined,
        parent: undefined,
        parents: undefined,
        path: '/home',
        show: true,
        children: [],
      },
      {
        badge: undefined,
        badgeType: undefined,
        badgeVariants: undefined,
        icon: 'about-icon',
        name: '关于',
        order: undefined,
        parent: undefined,
        parents: undefined,
        path: '/about',
        show: true,
        children: [],
      },
    ];

    const menus = generateMenus(mockRoutes, mockRouter as any);
    expect(menus).toEqual(expectedMenus);
  });

  it('includes additional meta properties in menu items', async () => {
    const mockRoutesWithMeta = [
      {
        meta: { icon: 'user-icon', order: 1, title: 'Profile' },
        name: 'profile',
        path: '/profile',
      },
    ] as RouteRecordRaw[];

    const menus = generateMenus(mockRoutesWithMeta, mockRouter as any);
    expect(menus).toEqual([
      {
        badge: undefined,
        badgeType: undefined,
        badgeVariants: undefined,
        icon: 'user-icon',
        name: 'Profile',
        order: 1,
        parent: undefined,
        parents: undefined,
        path: '/profile',
        show: true,
        children: [],
      },
    ]);
  });

  it('handles dynamic route parameters correctly', async () => {
    const mockRoutesWithParams = [
      {
        meta: { icon: 'details-icon', title: 'User Details' },
        name: 'userDetails',
        path: '/users/:userId',
      },
    ] as RouteRecordRaw[];

    const menus = generateMenus(mockRoutesWithParams, mockRouter as any);
    expect(menus).toEqual([
      {
        badge: undefined,
        badgeType: undefined,
        badgeVariants: undefined,
        icon: 'details-icon',
        name: 'User Details',
        order: undefined,
        parent: undefined,
        parents: undefined,
        path: '/users/:userId',
        show: true,
        children: [],
      },
    ]);
  });

  it('processes routes with redirects correctly', async () => {
    const mockRoutesWithRedirect = [
      {
        name: 'redirectedRoute',
        path: '/old-path',
        redirect: '/new-path',
      },
      {
        meta: { icon: 'path-icon', title: 'New Path' },
        name: 'newPath',
        path: '/new-path',
      },
    ] as RouteRecordRaw[];

    const menus = generateMenus(mockRoutesWithRedirect, mockRouter as any);
    expect(menus).toEqual([
      // Assuming your generateMenus function excludes redirect routes from the menu
      {
        badge: undefined,
        badgeType: undefined,
        badgeVariants: undefined,
        icon: undefined,
        name: 'redirectedRoute',
        order: undefined,
        parent: undefined,
        parents: undefined,
        path: '/old-path',
        show: true,
        children: [],
      },
      {
        badge: undefined,
        badgeType: undefined,
        badgeVariants: undefined,
        icon: 'path-icon',
        name: 'New Path',
        order: undefined,
        parent: undefined,
        parents: undefined,
        path: '/new-path',
        show: true,
        children: [],
      },
    ]);
  });

  const routes: any = [
    {
      meta: { order: 2, title: 'Home' },
      name: 'home',
      path: '/',
    },
    {
      meta: { order: 1, title: 'About' },
      name: 'about',
      path: '/about',
    },
  ];

  const router: Router = createRouter({
    history: createWebHistory(),
    routes,
  });

  it('should generate menu list with correct order', async () => {
    const menus = generateMenus(routes, router);
    const expectedMenus = [
      {
        badge: undefined,
        badgeType: undefined,
        badgeVariants: undefined,
        icon: undefined,
        name: 'About',
        order: 1,
        parent: undefined,
        parents: undefined,
        path: '/about',
        show: true,
        children: [],
      },
      {
        badge: undefined,
        badgeType: undefined,
        badgeVariants: undefined,
        icon: undefined,
        name: 'Home',
        order: 2,
        parent: undefined,
        parents: undefined,
        path: '/',
        show: true,
        children: [],
      },
    ];

    expect(menus).toEqual(expectedMenus);
  });

  it('should handle empty routes', async () => {
    const emptyRoutes: any[] = [];
    const menus = generateMenus(emptyRoutes, router);
    expect(menus).toEqual([]);
  });
});

describe('convertServerMenuToRouteRecordStringComponent', () => {
  it('keeps an absolute child path stable across menu regrouping', () => {
    const routes = convertServerMenuToRouteRecordStringComponent([
      {
        children: [
          {
            component: 'ai-video/model/index',
            componentName: 'AiVideoModel',
            id: 7040,
            name: '模型中心',
            parentId: 7150,
            path: '/ai-video/model',
            sort: 1,
            visible: true,
          },
        ],
        id: 7150,
        name: 'AI 能力',
        parentId: 0,
        path: '/ai-center',
        sort: 5,
        visible: true,
      },
    ] as any);

    expect(routes[0]?.children?.[0]?.path).toBe('/ai-video/model');
  });

  it('still joins a relative child path to its parent path', () => {
    const routes = convertServerMenuToRouteRecordStringComponent([
      {
        children: [
          {
            component: 'ai-video/camera/index',
            componentName: 'AiVideoCamera',
            id: 7010,
            name: '摄像头管理',
            parentId: 7000,
            path: 'camera',
            sort: 1,
            visible: true,
          },
        ],
        id: 7000,
        name: '视频监控',
        parentId: 0,
        path: '/ai-video',
        sort: 4,
        visible: true,
      },
    ] as any);

    expect(routes[0]?.children?.[0]?.path).toBe('/ai-video/camera');
  });
});
