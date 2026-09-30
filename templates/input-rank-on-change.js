     $('input.rank').on('change', function() {
       console.log("changed: ", $(this), this);
       const $curRank = $(this);
       const $prevRank = $curRank.prev();
       const $origRank = $prevRank.prev();
       const myNewVal = parseInt($curRank.val());
       const myPrevVal = parseInt($prevRank.val());
       const myOrigVal = parseInt($origRank.val());
       const incr = myNewVal < myPrevVal ? 1 : -1;

       let newVal = myNewVal;
       let $found = $('input.prev').filter(function() {
         return this.value == newVal;
       });
       while ($found) {
         let $fndPrev = $found;
         let $fndCur = $fndPrev.next();

         newVal += incr;
         $found = $('input.prev').filter(function() {
           return this.value == newVal;
         });
         $fndCur.val(newVal);
         $fndPrev.val(newVal);

         if (newVal == myPrevVal) {
           assert($found.is($prevRank));
           $prevRank.val(myNewVal);
           break;
         }
       }
