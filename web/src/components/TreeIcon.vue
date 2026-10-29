<script setup lang="ts">
// Tree icons: inline SVG (16×16, currentColor stroke), without external fonts and libraries.
defineProps<{ kind: string; dir?: string | null; hint?: string }>();
</script>

<template>
  <svg class="ticon" :class="[kind, dir]" viewBox="0 0 16 16" width="16" height="16" fill="none" stroke="currentColor"
       stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
    <title v-if="hint">{{ hint }}</title>
    <!-- document -->
    <template v-if="kind === 'document'">
      <path d="M4 1.5h5.5L12.5 4.5v10h-8.5z" /><path d="M9.5 1.5v3h3" /><path d="M6 8h4.5M6 10.5h4.5" />
    </template>
    <!-- revision history: a clock with an arrow back -->
    <template v-else-if="kind === 'history'">
      <path d="M2.6 8a5.4 5.4 0 1 0 1.6-3.8" /><path d="M2.3 2.3v2.6h2.6" /><path d="M8 5v3.2l2.2 1.4" />
    </template>
    <!-- history entry: a version label -->
    <template v-else-if="kind === 'revision'">
      <path d="M2 2.5h5.5l6.5 6.5-5 5-6.5-6.5z" /><circle cx="5" cy="5.5" r="1" />
    </template>
    <!-- bus: a trunk with drops -->
    <template v-else-if="kind === 'bus'">
      <path d="M1.5 6.5h13M1.5 9.5h13" /><path d="M4.5 9.5v3M8 9.5v3M11.5 9.5v3" /><circle cx="4.5" cy="13" r=".6" />
      <circle cx="8" cy="13" r=".6" /><circle cx="11.5" cy="13" r=".6" />
    </template>
    <!-- device: a chip on a board -->
    <template v-else-if="kind === 'device'">
      <rect x="4" y="4" width="8" height="8" rx="1" /><rect x="6.3" y="6.3" width="3.4" height="3.4" rx=".4" />
      <path d="M6 1.8V4M10 1.8V4M6 12v2.2M10 12v2.2M1.8 6H4M1.8 10H4M12 6h2.2M12 10h2.2" />
    </template>
    <!-- object dictionary of a device: a table of index rows -->
    <template v-else-if="kind === 'objects'">
      <rect x="2" y="2.5" width="12" height="11" rx="1" /><path d="M2 6h12M2 9.5h12M6 2.5v11" />
    </template>
    <!-- frame: a packet + the direction -->
    <template v-else-if="kind === 'frame'">
      <rect x="1.5" y="4.5" width="9" height="7" rx="1" /><path d="M3.5 7h2M3.5 9h4" />
      <!-- TX: sent by the device -->
      <path v-if="dir === 'tx'" d="M11 8h3.5M12.8 6.2 14.5 8l-1.7 1.8" />
      <!-- RX: a command to the device -->
      <path v-else-if="dir === 'rx'" d="M15 8h-3.5M13.2 6.2 11.5 8l1.7 1.8" />
      <!-- broadcast -->
      <template v-else><path d="M12.3 5.8a3 3 0 0 1 0 4.4" /><path d="M13.8 4.3a5.2 5.2 0 0 1 0 7.4" /></template>
    </template>
    <!-- signal -->
    <template v-else-if="kind === 'signal'">
      <path d="M1.5 10.5h2.5v-5h3v5h3v-5h2.5v5h2" />
    </template>
    <!-- flag of a bit field -->
    <template v-else-if="kind === 'flag'">
      <path d="M4 14.5V2" /><path d="M4 2.5h8l-1.8 2.8L12 8H4" />
    </template>
    <!-- SDO exchange -->
    <template v-else-if="kind === 'sdo'">
      <path d="M2 5.5h10.5M10.5 3.5l2 2-2 2" /><path d="M14 10.5H3.5M5.5 8.5l-2 2 2 2" />
    </template>
    <circle v-else cx="8" cy="8" r="1.5" />
  </svg>
</template>
