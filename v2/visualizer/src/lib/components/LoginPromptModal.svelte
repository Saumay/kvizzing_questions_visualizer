<script lang="ts">
  import { goto } from '$app/navigation';

  let { show = $bindable(false) }: { show?: boolean } = $props();
</script>

{#if show}
  <!-- svelte-ignore a11y_click_events_have_key_events -->
  <div
    class="fixed inset-0 z-[100] bg-black/40 flex items-center justify-center px-4"
    role="presentation"
    onclick={() => show = false}
  >
    <div
      class="w-full max-w-sm bg-white dark:bg-gray-800 rounded-2xl shadow-xl p-6"
      onclick={(e) => e.stopPropagation()}
      role="dialog"
      aria-modal="true"
      tabindex="-1"
    >
      <div class="flex items-center gap-3 mb-3">
        <div class="w-9 h-9 rounded-full bg-primary-100 dark:bg-primary-900/40 flex items-center justify-center flex-shrink-0">
          <svg class="w-4.5 h-4.5 text-primary-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
          </svg>
        </div>
        <h2 class="font-semibold text-gray-900 dark:text-white">Sign in to continue</h2>
      </div>
      <p class="text-sm text-gray-500 dark:text-gray-400 mb-5">
        Liking, saving, and flagging questions needs a KVizzing identity — sign in with Google to keep this action.
      </p>
      <div class="flex gap-2">
        <button
          onclick={() => { show = false; goto('/login'); }}
          class="flex-1 py-2 rounded-lg text-sm font-medium text-white bg-primary-500 hover:bg-primary-600 transition-colors"
        >Sign in</button>
        <button
          onclick={() => show = false}
          class="px-4 py-2 rounded-lg text-sm font-medium text-gray-500 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors"
        >Not now</button>
      </div>
    </div>
  </div>
{/if}
