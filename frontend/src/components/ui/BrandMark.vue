<script setup>
// The Zinvest logo: the sprout-and-dot symbol, in the brand colours wherever it
// appears. Size comes from the caller's class. On the dark theme the navy dot
// turns light, or it would disappear into the background.
import { SYMBOL_BLUE, SYMBOL_DOT, SYMBOL_SPROUT, SYMBOL_VIEWBOX } from './brandMark'
</script>

<template>
  <span class="flex shrink-0 items-center justify-center" aria-hidden="true">
    <svg :viewBox="SYMBOL_VIEWBOX" class="h-full w-full" focusable="false">
      <path :d="SYMBOL_SPROUT" :fill="SYMBOL_BLUE" />
      <circle v-bind="SYMBOL_DOT" class="brand-dot" />
    </svg>
  </span>
</template>

<style scoped>
.brand-dot {
  fill: #0a1128;
}
.dark .brand-dot {
  fill: #eef2ff;
}
</style>
