<script lang="ts">
  let { onAuthenticated }: { onAuthenticated: () => void } = $props();

  let input = $state('');
  let error = $state(false);

  const PHRASE = 'mischief managed';

  function isPhrase(raw: string): boolean {
    return raw.toLowerCase().replace(/\s+/g, ' ').trim() === PHRASE;
  }

  function handleKeydown(e: KeyboardEvent) {
    if (e.key !== 'Enter') return;
    if (isPhrase(input)) {
      onAuthenticated();
    } else {
      error = true;
      setTimeout(() => { error = false; }, 600);
    }
  }
</script>

<div class="h-dvh flex flex-col items-center justify-center gap-4 px-4 bg-ui-parchment">
  <span class="font-bold text-gray-900 dark:text-white text-2xl tracking-tight">KVizzing</span>
  <p class="text-sm text-gray-500 dark:text-gray-400">Gotta type the right words to enter in..</p>
  <input
    type="text"
    bind:value={input}
    onkeydown={handleKeydown}
    autocomplete="off"
    spellcheck="false"
    autofocus
    class="w-72 text-center text-sm border-b border-gray-300 dark:border-gray-600 bg-transparent px-2 py-1.5 text-gray-800 dark:text-gray-200 focus:outline-none focus:border-primary-400 transition-colors {error ? 'border-red-400 animate-shake' : ''}"
  />
</div>

<style>
  @keyframes shake {
    0%, 100% { transform: translateX(0); }
    20%       { transform: translateX(-6px); }
    40%       { transform: translateX(6px); }
    60%       { transform: translateX(-4px); }
    80%       { transform: translateX(4px); }
  }
  .animate-shake {
    animation: shake 0.4s ease;
  }
</style>
