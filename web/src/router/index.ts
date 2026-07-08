import { createRouter, createWebHistory } from "vue-router";

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: "/",
      redirect: "/chat",
    },
    {
      path: "/chat",
      name: "chat",
      component: () => import("@/views/ChatView.vue"),
      meta: { persona: "consumer", title: "智能助手" },
    },
    {
      path: "/chat/:sessionId",
      name: "chat-session",
      component: () => import("@/views/ChatView.vue"),
      meta: { persona: "consumer", title: "智能助手" },
    },
    {
      path: "/ops",
      name: "ops",
      component: () => import("@/views/OpsView.vue"),
      meta: { persona: "merchant", title: "商家运营" },
    },
    {
      path: "/ops/:sessionId",
      name: "ops-session",
      component: () => import("@/views/OpsView.vue"),
      meta: { persona: "merchant", title: "商家运营" },
    },
    {
      path: "/rag",
      name: "rag",
      component: () => import("@/views/RagView.vue"),
      meta: { title: "RAG 知识库" },
    },
  ],
});

router.afterEach((to) => {
  const title = (to.meta.title as string) ?? "Herness Agent";
  document.title = `${title} · Herness`;
});

export default router;
