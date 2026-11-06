<!-- homedock-ui/vue3/static/js/__Components__/TopComment.vue -->
<!-- Copyright © 2023-2026 Banshee, All Rights Reserved -->
<!-- https://www.banshee.pro -->

<template></template>

<script setup lang="ts">
import { onMounted } from "vue";

const commentContent = `
<!--                                            -->
<!--             @@@@@@@@@@@@@@@@@@@@@@@@       -->
<!--            @@@@@@@@@@@@@@@@@@@@@@@@@       -->
<!--           @@@@                             -->
<!--          @@@@   @@@@@@@@@@@@@@@@@@@@       -->
<!--         @@@@   @@@                         -->
<!--         @@@   @@@   @@@@@@@@@@@@@          -->
<!--        @@@   @@@*  @@@@      @@@*  @       -->
<!--       @@@   @@@@  @@@@      @@@@  @@       -->
<!--      @@@*  @@@@  (@@@      @@@@@@@@@       -->
<!--     @@@@  @@@@   @@@      //////////       -->
<!--    @@@@  @@@@   @@@                        -->
<!--   @@@@  #@@@   @@@                         -->
<!--  @@@@   @@@   @@@                          -->
<!--                                            -->
<!--  Take Control of the Cloud with            -->
<!--  HomeDock OS, on the machine you           -->
<!--  already own.                              -->
<!--                                            -->
<!--  Like what you see? A star on GitHub       -->
<!--  keeps a small team building:              -->
<!--  https://github.com/BansheeTech/HomeDockOS -->
<!--                                            -->
<!--  HomeDock OS comes with                    -->
<!--  ABSOLUTELY NO WARRANTY, to the extent     -->
<!--  permitted by applicable law.              -->
<!--                                            -->
<!--  https://www.homedock.cloud                -->
<!--                                            -->
<!--  Copyright © 2023-2026 Banshee             -->
<!--  All Rights Reserved                       -->
<!--  https://www.banshee.pro                   -->
<!--                                            -->
`;

onMounted(() => {
  console.log(
    `
%c             @@@@@@@@@@@@@@@@@@@@@@@@
%c            @@@@@@@@@@@@@@@@@@@@@@@@@
%c           @@@@                             
%c          @@@@   @@@@@@@@@@@@@@@@@@@@       
%c         @@@@   @@@                         
%c         @@@   @@@   @@@@@@@@@@@@@          
%c        @@@   @@@*  @@@@      @@@*  @       
%c       @@@   @@@@  @@@@      @@@@  @@       
%c      @@@*  @@@@  (@@@      @@@@@@@@@       
%c     @@@@  @@@@   @@@      //////////       
%c    @@@@  @@@@   @@@                        
%c   @@@@  #@@@   @@@                         
%c  @@@@   @@@   @@@                          
%c
%c  Take Control of the Cloud with HomeDock OS
%c
%c  🌍 Website: https://www.homedock.cloud
%c  📖 Documentation: https://docs.homedock.cloud
%c  🐤 Discord: https://discord.gg/Zj3JCYsRWw
%c  🧑‍💻 GitHub: https://github.com/BansheeTech/HomeDockOS
`,
    "color: #FFFFFF; font-weight: bold; font-size: 10px;",
    "color: #EEEEEE; font-weight: bold; font-size: 10px;",
    "color: #DDDDDD; font-weight: bold; font-size: 10px;",
    "color: #CCCCCC; font-weight: bold; font-size: 10px;",
    "color: #BBBBBB; font-weight: bold; font-size: 10px;",
    "color: #AAAAAA; font-weight: bold; font-size: 10px;",
    "color: #999999; font-weight: bold; font-size: 10px;",
    "color: #888888; font-weight: bold; font-size: 10px;",
    "color: #777777; font-weight: bold; font-size: 10px;",
    "color: #666666; font-weight: bold; font-size: 10px;",
    "color: #555555; font-weight: bold; font-size: 10px;",
    "color: #444444; font-weight: bold; font-size: 10px;",
    "color: #333333; font-weight: bold; font-size: 10px;",
    "color: #222222; font-weight: bold; font-size: 10px;",
    "color: #FFFFFF; font-weight: bold; font-size: 10px;",
    "color: #FFFFFF; font-weight: bold; font-size: 10px;",
    "color: #FFFFFF; font-weight: bold; font-size: 10px;",
    "color: #FFFFFF; font-weight: bold; font-size: 10px;",
    "color: #FFFFFF; font-weight: bold; font-size: 10px;",
    "color: #FFFFFF; font-weight: bold; font-size: 10px;"
  );

  const commentNode = document.createComment(commentContent);
  document.body.insertBefore(commentNode, document.body.firstChild);
});
</script>
